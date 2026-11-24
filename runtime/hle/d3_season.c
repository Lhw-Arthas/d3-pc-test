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

// 菜单下拉列表对应的 18 个社区 Buff（2.7.6 与 2.7.7 地址完全一致）
typedef struct { const char *key; const char *label; uint32_t off; } buff_t;
static const buff_t k_buffs[NBUFF] = {
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

static const struct { int season; uint32_t mask; } k_themes[] = {
    {14, 1u << 2},  {15, 1u << 3},  {16, 1u << 4},  {17, 1u << 5},  {18, 1u << 6},
    {19, 1u << 7},  {20, 1u << 8},  {21, 1u << 9},  {22, (1u << 10) | (1u << 11)},
    {24, 1u << 12}, {25, 1u << 13}, {26, 1u << 14}, {27, 1u << 15}, {28, 1u << 16},
    {29, 1u << 17}, {30, 1u << 13}, {31, 1u << 8},  {32, 1u << 12}, {33, (1u << 10) | (1u << 11)},
    {34, 1u << 15}, {35, 1u << 7},  {36, 1u << 13}, {37, 1u << 8},
};

typedef struct {
    bool     is_276;
    uint32_t bool_set;
    uint32_t u32_set;
    // 2.7.7 直接偏移 (is_276 == false 时使用)
    uint32_t season_num;
    uint32_t season_state;
    uint32_t season_ovr;
    uint32_t ev_enabled;
    uint32_t ev_seasononly;
    uint32_t buff_start;
    uint32_t buff_end;
    uint32_t ui_season_opt;
    uint32_t ui_season_flag;
    // 2.7.6 指针表偏移 (is_276 == true 时使用，来自 d3hack offsets_patch_only.inl)
    uint32_t season_num_ptr;
    uint32_t season_state_ptr;
    uint32_t season_ovr_ptr;
    uint32_t ev_enabled_ptr;
    uint32_t ev_seasononly_ptr;
    uint32_t buff_start_ptr;
    uint32_t buff_end_ptr;
} d3_season_cfg_t;

static const d3_season_cfg_t k_cfg_277 = {
    .is_276         = false,
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
};

static const d3_season_cfg_t k_cfg_276 = {
    .is_276            = true,
    .bool_set          = 0xa26ec0,  // sym_XVarBool_Set
    .u32_set           = 0xa272c0,  // sym_XVarUint32_Set
    .season_num_ptr    = 0x114ac60, // xvar_season_num_ptr
    .season_state_ptr  = 0x114ac68, // xvar_season_state_ptr
    .season_ovr_ptr    = 0x11590d8, // xvar_seasons_override_enabled_ptr
    .ev_enabled_ptr    = 0x114acd8, // event_enabled
    .ev_seasononly_ptr = 0x114ace8, // event_season_only
    .buff_start_ptr    = 0x114acb8, // event_buff_start
    .buff_end_ptr      = 0x114acc0, // event_buff_end
};

static const d3_season_cfg_t *g_cfg = &k_cfg_277;
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

    const GameVersion *v = game_version();
    if (v && v->key && strcmp(v->key, "d3_2_7_6") == 0) {
        g_cfg = &k_cfg_276;
    } else {
        g_cfg = &k_cfg_277;
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
            char buf;
            snprintf(buf, sizeof buf, "%s", et);
            g_settings.d3_theme_auto = false;
            g_settings.d3_themes_mask = 0;
            char *tok = strtok(buf, ",");
            while (tok) {
                if (!strcmp(tok, "auto")) g_settings.d3_theme_auto = true;
                else {
                    for (int i = 0; i < NBUFF; i++) {
                        if (!strcmp(tok, k_buffs[i].key)) {
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

static inline uint64_t read_guest_ptr(uint32_t ptr_off) {
    if (!ptr_off) return 0;
    return *(volatile uint64_t *)(uintptr_t)(MAIN_BASE + ptr_off);
}

static void call_xvar_bool_addr(Cpu *c, uint64_t addr, int val) {
    if (addr < MAIN_BASE) return;
    if ((*(volatile uint8_t *)(uintptr_t)(addr + 0xb0) & 1) == (val & 1)) return;
    Cpu save = *c;
    c->x = addr;
    c->x = (uint64_t)(val & 1);
    c->x = 3;
    guest_call(c, MAIN_BASE + g_cfg->bool_set);
    *c = save;
}

static void call_xvar_u32_addr(Cpu *c, uint64_t addr, uint32_t val) {
    if (addr < MAIN_BASE) return;
    if (*(volatile uint32_t *)(uintptr_t)(addr + 0xb0) == val) return;
    Cpu save = *c;
    c->x = addr;
    c->x = val;
    c->x = 3;
    guest_call(c, MAIN_BASE + g_cfg->u32_set);
    *c = save;
}

static void apply_xvars(Cpu *c) {
    int season = d3_offline_season_num();
    uint32_t mask = current_buff_mask(season);

    uint64_t addr_season_num    = g_cfg->is_276 ? read_guest_ptr(g_cfg->season_num_ptr)    : (MAIN_BASE + g_cfg->season_num);
    uint64_t addr_season_state  = g_cfg->is_276 ? read_guest_ptr(g_cfg->season_state_ptr)  : (MAIN_BASE + g_cfg->season_state);
    uint64_t addr_season_ovr    = g_cfg->is_276 ? read_guest_ptr(g_cfg->season_ovr_ptr)    : (MAIN_BASE + g_cfg->season_ovr);
    uint64_t addr_ev_enabled    = g_cfg->is_276 ? read_guest_ptr(g_cfg->ev_enabled_ptr)    : (MAIN_BASE + g_cfg->ev_enabled);
    uint64_t addr_ev_seasononly = g_cfg->is_276 ? read_guest_ptr(g_cfg->ev_seasononly_ptr) : (MAIN_BASE + g_cfg->ev_seasononly);

    if (season > 0) {
        call_xvar_u32_addr(c, addr_season_num, (uint32_t)season);
        call_xvar_u32_addr(c, addr_season_state, 1);
        call_xvar_bool_addr(c, addr_season_ovr, 1);
        if (!g_cfg->is_276) {
            *(volatile uint32_t *)(uintptr_t)(MAIN_BASE + g_cfg->ui_season_opt) = 1;
            *(volatile uint32_t *)(uintptr_t)(MAIN_BASE + g_cfg->ui_season_flag) = 1;
        }
    } else {
        call_xvar_u32_addr(c, addr_season_state, 0);
        call_xvar_bool_addr(c, addr_season_ovr, 0);
    }

    if (mask != 0) {
        int64_t *t0 = (int64_t *)(uintptr_t)(g_cfg->is_276 ? read_guest_ptr(g_cfg->buff_start_ptr) : (MAIN_BASE + g_cfg->buff_start));
        int64_t *t1 = (int64_t *)(uintptr_t)(g_cfg->is_276 ? read_guest_ptr(g_cfg->buff_end_ptr)   : (MAIN_BASE + g_cfg->buff_end));
        if ((uintptr_t)t0 >= MAIN_BASE && (uintptr_t)t1 >= MAIN_BASE) {
            if (!*t0 || !*t1 || *t1 <= *t0) { *t0 = 1; *t1 = INT64_MAX; }
        }
        for (int i = 0; i < NBUFF; i++) {
            call_xvar_bool_addr(c, MAIN_BASE + k_buffs[i].off, (mask >> i) & 1);
        }
        call_xvar_bool_addr(c, addr_ev_seasononly, 0);
        call_xvar_bool_addr(c, addr_ev_enabled, 1);
    } else {
        for (int i = 0; i < NBUFF; i++) {
            call_xvar_bool_addr(c, MAIN_BASE + k_buffs[i].off, 0);
        }
        call_xvar_bool_addr(c, addr_ev_enabled, 0);
    }
}

void d3_season_run(Cpu *c) {
    static unsigned polls = 0;
    bool need = atomic_exchange(&g_dirty, false);
    if (!need && (++polls % 180 != 0)) return;
    if (g_settings.d3_season == 0 && !g_settings.d3_theme_auto && g_settings.d3_themes_mask == 0 && !need) return;
    apply_xvars(c);
}
