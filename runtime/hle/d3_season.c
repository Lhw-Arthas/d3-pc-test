// source/runtime/hle/d3_season.c
#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "../cpu.h"
#include "../game_addresses.h"
#include "../hle.h"
#include "../settings.h"

extern void guest_call(Cpu *c, uint64_t addr);

#define MAIN_BASE 0x7000000000ull

enum {
    OFF_BOOL_SET      = 0xa26fc0,
    OFF_U32_SET       = 0xa273c0,
    OFF_SEASON_NUM    = 0x1a1bd78,
    OFF_SEASON_STATE  = 0x1a1be30,
    OFF_SEASON_OVR    = 0x1a1c1c8,
    OFF_EV_ENABLED    = 0x18ffbe0,
    OFF_EV_SEASONONLY = 0x18ffc98,
    OFF_BUFF_START    = 0x1771758,
    OFF_BUFF_END      = 0x1771760,
};

// 菜单下拉列表对应的 18 个社区 Buff（索引 0=Off, 1=Auto, 2..19 对应下列 18 项）
typedef struct { const char *key; const char *label; uint32_t off; } buff_t;
static const buff_t k_buffs[] = {
    {"keystones",   "Double Rift Keystones",      0x18fffc8}, // 2
    {"bloodshards", "Double Blood Shards",        0x1900080}, // 3
    {"goblins",     "S14: Double Goblins",        0x1900138}, // 4
    {"bags",        "S15: Double Bounty Bags",    0x19001f0}, // 5
    {"grandeur",    "S16: Royal Grandeur",        0x19002a8}, // 6
    {"nightmares",  "S17: Legacy of Nightmares",  0x1900360}, // 7
    {"triune",      "S18: Triune's Will",         0x1900418}, // 8
    {"pandemonium", "S19/35: Pandemonium",        0x19004d0}, // 9
    {"kanai",       "S20/31/37: Kanai Powers",    0x1900588}, // 10
    {"tempests",    "S21: Trials of Tempests",    0x1900640}, // 11
    {"clones",      "S22/33: Shadow Clones",      0x19006f8}, // 12
    {"cube4",       "S22/33: 4th Cube Slot",      0x19007b0}, // 13
    {"ethereal",    "S24/32: Ethereal Items",     0x1900868}, // 14
    {"shards",      "S25/30/36: Soul Shards",     0x1900920}, // 15
    {"swarm",       "S26: Echoing Nightmares",    0x19009d8}, // 16
    {"sanctified",  "S27/34: Sanctified Items",   0x1900a90}, // 17
    {"alchemy",     "S28: Altar of Rites",        0x1900b48}, // 18
    {"nesting",     "S29: Visions of Enmity",     0x18ff848}, // 19
};
#define NBUFF (int)(sizeof k_buffs / sizeof *k_buffs)

static const struct { int season; uint32_t mask; } k_themes[] = {
    {14, 1u << 2},  {15, 1u << 3},  {16, 1u << 4},  {17, 1u << 5},  {18, 1u << 6},
    {19, 1u << 7},  {20, 1u << 8},  {21, 1u << 9},  {22, (1u << 10) | (1u << 11)},
    {24, 1u << 12}, {25, 1u << 13}, {26, 1u << 14}, {27, 1u << 15}, {28, 1u << 16},
    {29, 1u << 17}, {30, 1u << 13}, {31, 1u << 8},  {32, 1u << 12}, {33, (1u << 10) | (1u << 11)},
    {34, 1u << 15}, {35, 1u << 7},  {36, 1u << 13}, {37, 1u << 8},
};

static _Atomic bool g_dirty = true;
RT_ON_RESET(d3_season_reset) { atomic_store(&g_dirty, true); }

// 供 menu.mm 主动触发立即刷新
void d3_season_mark_dirty(void) { atomic_store(&g_dirty, true); }

// 供 d3_gen_patch.py 生成的代码调用
int d3_offline_season_num(void) {
    int s = g_settings.d3_season;
    return (s >= 1 && s <= 99) ? s : 0;
}

static uint32_t current_buff_mask(int season, int theme_choice) {
    if (theme_choice <= 0) return 0;
    if (theme_choice == 1) { // Auto: 自动匹配赛季主题
        for (size_t i = 0; i < sizeof k_themes / sizeof *k_themes; i++) {
            if (k_themes[i].season == season) return k_themes[i].mask;
        }
        return 0;
    }
    int idx = theme_choice - 2;
    return (idx >= 0 && idx < NBUFF) ? (1u << idx) : 0;
}

// 在 main.c 的 boot() 中调用：支持环境变量作为初始默认值
void d3_season_init(void) {
    if (!game_is_d3()) return;
    const char *es = getenv("D3_SEASON");
    if (es && *es) {
        int s = atoi(es);
        if (s >= 0 && s <= 99) g_settings.d3_season = s;
    }
    const char *et = getenv("D3_THEME");
    if (et && *et) {
        if (!strcmp(et, "auto")) g_settings.d3_theme = 1;
        else if (!strcmp(et, "0") || !strcmp(et, "off")) g_settings.d3_theme = 0;
        else {
            for (int i = 0; i < NBUFF; i++) {
                if (!strcmp(et, k_buffs[i].key)) { g_settings.d3_theme = i + 2; break; }
            }
        }
    }
    atomic_store(&g_dirty, true);
}

static void call_xvar_bool(Cpu *c, uint32_t off, int val) {
    uint64_t addr = MAIN_BASE + off;
    if ((*(volatile uint8_t *)(uintptr_t)(addr + 0xb0) & 1) == (val & 1)) return;
    Cpu save = *c;
    c->x[0] = addr;
    c->x[1] = (uint64_t)(val & 1);
    c->x[2] = 3;
    guest_call(c, MAIN_BASE + OFF_BOOL_SET);
    *c = save;
}

static void call_xvar_u32(Cpu *c, uint32_t off, uint32_t val) {
    uint64_t addr = MAIN_BASE + off;
    if (*(volatile uint32_t *)(uintptr_t)(addr + 0xb0) == val) return;
    Cpu save = *c;
    c->x[0] = addr;
    c->x[1] = val;
    c->x[2] = 3;
    guest_call(c, MAIN_BASE + OFF_U32_SET);
    *c = save;
}

static void apply_xvars(Cpu *c) {
    int season = d3_offline_season_num();
    uint32_t mask = current_buff_mask(season, g_settings.d3_theme);

    if (season > 0) {
        call_xvar_u32(c, OFF_SEASON_NUM, (uint32_t)season);
        call_xvar_u32(c, OFF_SEASON_STATE, 1);
        call_xvar_bool(c, OFF_SEASON_OVR, 1);
    } else {
        call_xvar_u32(c, OFF_SEASON_STATE, 0);
        call_xvar_bool(c, OFF_SEASON_OVR, 0);
    }

    if (mask != 0) {
        int64_t *t0 = (int64_t *)(uintptr_t)(MAIN_BASE + OFF_BUFF_START);
        int64_t *t1 = (int64_t *)(uintptr_t)(MAIN_BASE + OFF_BUFF_END);
        if (!*t0 || !*t1 || *t1 <= *t0) { *t0 = 1; *t1 = INT64_MAX; }
        for (int i = 0; i < NBUFF; i++) {
            call_xvar_bool(c, k_buffs[i].off, (mask >> i) & 1);
        }
        call_xvar_bool(c, OFF_EV_SEASONONLY, 0);
        call_xvar_bool(c, OFF_EV_ENABLED, 1);
    } else {
        for (int i = 0; i < NBUFF; i++) {
            call_xvar_bool(c, k_buffs[i].off, 0);
        }
        call_xvar_bool(c, OFF_EV_ENABLED, 0);
    }
}

void d3_season_run(Cpu *c) {
    static unsigned polls = 0;
    bool need = atomic_exchange(&g_dirty, false);
    if (!need && (++polls % 180 != 0)) return; // 菜单改动时立即应用，平时每 ~3 秒维护一次
    if (g_settings.d3_season == 0 && g_settings.d3_theme == 0 && !need) return;
    apply_xvars(c);
}
