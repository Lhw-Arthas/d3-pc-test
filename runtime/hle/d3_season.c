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
#define NBUFF 18

typedef struct {
    uint32_t bool_set;
    uint32_t u32_set;
    uint32_t season_num;
    uint32_t season_state;
    uint32_t season_ovr;
    uint32_t ev_enabled;
    uint32_t ev_seasononly;
    uint32_t buff_start;
    uint32_t buff_end;
    uint32_t ui_season_opt;
    uint32_t ui_season_flag;
    uint32_t buffs[NBUFF];
} d3_season_addrs_t;

// 2.7.7 偏移表（保持你原有的验证地址不变）
static const d3_season_addrs_t k_addrs_277 = {
    .bool_set       = 0xa26fc0,
    .u32_set        = 0xa273c0,
    .season_num     = 0x1a1bd78,
    .season_state   = 0x1a1be30,
    .season_ovr     = 0x1a1c1c8,
    .ev_enabled     = 0x18ffbe0,
    .ev_seasononly  = 0x18ffc98,
    .buff_start     = 0x1771758,
    .buff_end       = 0x1771760,
    .ui_season_opt  = 0x18626b8,
    .ui_season_flag = 0x18627a4,
    .buffs = {
        0x18fffc8, // 2:  keystones
        0x1900080, // 3:  bloodshards
        0x1900138, // 4:  goblins
        0x19001f0, // 5:  bags
        0x19002a8, // 6:  grandeur
        0x1900360, // 7:  nightmares
        0x1900418, // 8:  triune
        0x19004d0, // 9:  pandemonium
        0x1900588, // 10: kanai
        0x1900640, // 11: tempests
        0x19006f8, // 12: clones
        0x19007b0, // 13: cube4
        0x1900868, // 14: ethereal
        0x1900920, // 15: shards
        0x19009d8, // 16: swarm
        0x1900a90, // 17: sanctified
        0x1900b48, // 18: alchemy
        0x18ff848, // 19: nesting
    }
};

// 2.7.6 偏移表（函数偏移已通过 d3hack offsets.hpp 精确修正）
// 注：下列数据段偏移若在 2.7.6 中测试未生效，可按下方说明调整差值
static const d3_season_addrs_t k_addrs_276 = {
    .bool_set       = 0xa26ec0, // 2.7.6 sym_XVarBool_Set
    .u32_set        = 0xa272c0, // 2.7.6 sym_XVarUint32_Set
    .season_num     = 0x1a1bd78,
    .season_state   = 0x1a1be30,
    .season_ovr     = 0x1a1c1c8,
    .ev_enabled     = 0x18ffbe0,
    .ev_seasononly  = 0x18ffc98,
    .buff_start     = 0x1771758,
    .buff_end       = 0x1771760,
    .ui_season_opt  = 0x18626b8,
    .ui_season_flag = 0x18627a4,
    .buffs = {
        0x18fffc8, 0x1900080, 0x1900138, 0x19001f0, 0x19002a8, 0x1900360,
        0x1900418, 0x19004d0, 0x1900588, 0x1900640, 0x19006f8, 0x19007b0,
        0x1900868, 0x1900920, 0x19009d8, 0x1900a90, 0x1900b48, 0x18ff848,
    }
};

static const char *const k_buff_keys[NBUFF] = {
    "keystones", "bloodshards", "goblins", "bags", "grandeur", "nightmares",
    "triune", "pandemonium", "kanai", "tempests", "clones", "cube4",
    "ethereal", "shards", "swarm", "sanctified", "alchemy", "nesting"
};

static const struct { int season; uint32_t mask; } k_themes[] = {
    {14, 1u << 2},  {15, 1u << 3},  {16, 1u << 4},  {17, 1u << 5},  {18, 1u << 6},
    {19, 1u << 7},  {20, 1u << 8},  {21, 1u << 9},  {22, (1u << 10) | (1u << 11)},
    {24, 1u << 12}, {25, 1u << 13}, {26, 1u << 14}, {27, 1u << 15}, {28, 1u << 16},
    {29, 1u << 17}, {30, 1u << 13}, {31, 1u << 8},  {32, 1u << 12}, {33, (1u << 10) | (1u << 11)},
    {34, 1u << 15}, {35, 1u << 7},  {36, 1u << 13}, {37, 1u << 8},
};

static const d3_season_addrs_t *g_addrs = &k_addrs_277;
static _Atomic bool g_dirty = true;
RT_ON_RESET(d3_season_reset) { atomic_store(&g_dirty, true); }

void d3_season_mark_dirty(void) { atomic_store(&g_dirty, true); }

int d3_offline_season_num(void) {
    int s = g_settings.d3_season;
    return (s >= 1 && s <= 99) ? s : 0;
}

static uint32_t current_buff_mask(int season) {
    uint32_t mask = g_settings.d3_themes_mask;
    if (g_settings.d3_theme_auto && season > 0) {
        for (size_t i = 0; i < sizeof k_themes / sizeof *k_themes; i++) {
            if (k_themes[i].season == season) {
                mask |= k_themes[i].mask;
                break;
            }
        }
    }
    return mask;
}

void d3_season_init(void) {
    if (!game_is_d3()) return;

    // 直接使用 game_addresses.h 的版本接口选择偏移表
    const GameVersion *v = game_version();
    if (v && v->key && strcmp(v->key, "d3_2_7_6") == 0) {
        g_addrs = &k_addrs_276;
    } else {
        g_addrs = &k_addrs_277;
    }

    const char *es = getenv("D3_SEASON");
    if (es && *es) {
        int s = atoi(es);
        if (s >= 0 && s <= 99) g_settings.d3_season = s;
    }
    const char *et = getenv("D3_THEME");
    if (et && *et) {
        if (!strcmp(et, "0") || !strcmp(et, "off")) {
            g_settings.d3_theme_auto = false;
            g_settings.d3_themes_mask = 0;
        } else {
            char buf[256];
            snprintf(buf, sizeof buf, "%s", et);
            g_settings.d3_theme_auto = false;
            g_settings.d3_themes_mask = 0;
            char *tok = strtok(buf, ",");
            while (tok) {
                if (!strcmp(tok, "auto")) g_settings.d3_theme_auto = true;
                else {
                    for (int i = 0; i < NBUFF; i++) {
                        if (!strcmp(tok, k_buff_keys[i])) {
                            g_settings.d3_themes_mask |= (1u << i);
                            break;
                        }
                    }
                }
                tok = strtok(NULL, ",");
            }
        }
    }
    atomic_store(&g_dirty, true);
}

static void call_xvar_bool(Cpu *c, uint32_t off, int val) {
    if (!off) return;
    uint64_t addr = MAIN_BASE + off;
    if ((*(volatile uint8_t *)(uintptr_t)(addr + 0xb0) & 1) == (val & 1)) return;
    Cpu save = *c;
    c->x[0] = addr;
    c->x[1] = (uint64_t)(val & 1);
    c->x[2] = 3;
    guest_call(c, MAIN_BASE + g_addrs->bool_set);
    *c = save;
}

static void call_xvar_u32(Cpu *c, uint32_t off, uint32_t val) {
    if (!off) return;
    uint64_t addr = MAIN_BASE + off;
    if (*(volatile uint32_t *)(uintptr_t)(addr + 0xb0) == val) return;
    Cpu save = *c;
    c->x[0] = addr;
    c->x[1] = val;
    c->x[2] = 3;
    guest_call(c, MAIN_BASE + g_addrs->u32_set);
    *c = save;
}

static void apply_xvars(Cpu *c) {
    int season = d3_offline_season_num();
    uint32_t mask = current_buff_mask(season);

    if (season > 0) {
        call_xvar_u32(c, g_addrs->season_num, (uint32_t)season);
        call_xvar_u32(c, g_addrs->season_state, 1);
        call_xvar_bool(c, g_addrs->season_ovr, 1);
        if (g_addrs->ui_season_opt)
            *(volatile uint32_t *)(uintptr_t)(MAIN_BASE + g_addrs->ui_season_opt) = 1;
        if (g_addrs->ui_season_flag)
            *(volatile uint32_t *)(uintptr_t)(MAIN_BASE + g_addrs->ui_season_flag) = 1;
    } else {
        call_xvar_u32(c, g_addrs->season_state, 0);
        call_xvar_bool(c, g_addrs->season_ovr, 0);
    }

    if (mask != 0) {
        int64_t *t0 = (int64_t *)(uintptr_t)(MAIN_BASE + g_addrs->buff_start);
        int64_t *t1 = (int64_t *)(uintptr_t)(MAIN_BASE + g_addrs->buff_end);
        if (!*t0 || !*t1 || *t1 <= *t0) { *t0 = 1; *t1 = INT64_MAX; }
        for (int i = 0; i < NBUFF; i++) {
            call_xvar_bool(c, g_addrs->buffs[i], (mask >> i) & 1);
        }
        call_xvar_bool(c, g_addrs->ev_seasononly, 0);
        call_xvar_bool(c, g_addrs->ev_enabled, 1);
    } else {
        for (int i = 0; i < NBUFF; i++) {
            call_xvar_bool(c, g_addrs->buffs[i], 0);
        }
        call_xvar_bool(c, g_addrs->ev_enabled, 0);
    }
}

void d3_season_run(Cpu *c) {
    static unsigned polls = 0;
    bool need = atomic_exchange(&g_dirty, false);
    if (!need && (++polls % 180 != 0)) return;
    if (g_settings.d3_season == 0 && !g_settings.d3_theme_auto && g_settings.d3_themes_mask == 0 && !need) return;
    apply_xvars(c);
}
