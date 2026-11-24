"""2.7.6-specific patch for generated Diablo III C code.
Run only on freshly generated 2.7.6 code. Changed files are backed up under backups/generated (same location as the original patcher).
Season-drop logic is mapped from the supplied 2.7.6 cheat instructions:
  0x492EF0: 0x14000005 -> B to 0x492F04
  0x897888: 0x52800020 -> MOV W0, #1
  0x89788C: 0x1400001A -> B to 0x8978F4
The source-level equivalents below activate only when d3_offline_season_num() > 0.
Address mappings from the 2.7.7 -> 2.7.6 signature report are otherwise unchanged.
"""
import os
import glob
import shutil
import sys
import re

GEN = r'<project folder>\src\d3recomp\generated\main'
BACKUP = r'<project folder>\backups\generated'

# 格式: (anchor (必须全局唯一), text inserted after it, declaration added after the first #include block)
PATCHES = [
 # 14. the game's event helpers (main+0x6900 signal / 0x6910 wait / 0x6920 timed wait): D3_CLOCK_LOG=4 logs the
 #     frame event's users (d3_clock.c)
 ('void f_7000006900(Cpu *c) {\n    FN_ENTER(0x7000006900ull);\n',
  "    d3_lock_seen(c->x[0], 'S', c->x[30]);  /* d3_gen_patch_276.py */\n",
  'void d3_lock_seen(uint64_t m, int unlock, uint64_t lr);  /* d3_gen_patch_276.py */\n'),
 ('void f_7000006910(Cpu *c) {\n    FN_ENTER(0x7000006910ull);\n',
  "    d3_lock_seen(c->x[0], 'W', c->x[30]);  /* d3_gen_patch_276.py */\n",
  'void d3_lock_seen(uint64_t m, int unlock, uint64_t lr);  /* d3_gen_patch_276.py */\n'),
 ('void f_7000006920(Cpu *c) {\n    FN_ENTER(0x7000006920ull);\n',
  "    d3_lock_seen(c->x[1], 'T', c->x[30]);  /* d3_gen_patch_276.py */\n",
  'void d3_lock_seen(uint64_t m, int unlock, uint64_t lr);  /* d3_gen_patch_276.py */\n'),
 # 13. the game's lock / unlock helpers (main+0x68b0 / 0x68c0): D3_CLOCK_LOG=4 logs the world lock's users (d3_clock.c)
 ('void f_70000068b0(Cpu *c) {\n    FN_ENTER(0x70000068b0ull);\n',
  '    d3_lock_seen(c->x[0], 0, c->x[30]);  /* d3_gen_patch_276.py */\n',
  'void d3_lock_seen(uint64_t m, int unlock, uint64_t lr);  /* d3_gen_patch_276.py */\n'),
 ('void f_70000068c0(Cpu *c) {\n    FN_ENTER(0x70000068c0ull);\n',
  '    d3_lock_seen(c->x[0], 1, c->x[30]);  /* d3_gen_patch_276.py (unlock) */\n',
  'void d3_lock_seen(uint64_t m, int unlock, uint64_t lr);  /* d3_gen_patch_276.py */\n'),
 # 11. the game's world step (main+0x7b7520, entered once per 1/60 s step): counted (hle/d3_clock.c d3_tick_mark)
 ('void f_70007b7520(Cpu *c) {\n    FN_ENTER(0x70007b7520ull);\n',
  '    d3_tick_mark();  /* d3_gen_patch_276.py */\n',
  'void d3_tick_mark(void);  /* d3_gen_patch_276.py */\n'),
 # 1. main menu's "is this entry shown"
 ('void f_700035bf80(Cpu *c) {\n    FN_ENTER(0x700035bf80ull);\n',
  '    { int h_ = d3_menu_hidden((uint32_t)c->x[0], (uint32_t)c->x[1]); if (h_) { c->x[0] = h_ == 2; return; } }  /* d3_gen_patch_276.py */\n',
  'int d3_menu_hidden(uint32_t menu, uint32_t id);  /* d3_gen_patch_276.py */\n'),
 # 5. the main menu's button handler (main+0x361780): entry 12 opens our settings menu (d3_menu.c d3_pc_settings_entry)
 ('    { uint64_t ea = c->x[9] + (c->x[8] << 2); uint64_t v = LD32(ea); c->x[8] = (uint64_t)(v); }\nL_700036181c:;\n',
  '    { int r_ = d3_pc_settings_entry((uint32_t)c->x[8]); if (r_ < 0) goto L_70003617a4; c->x[8] = (uint32_t)r_; }  /* d3_gen_patch_276.py */\n',
  'int d3_pc_settings_entry(uint32_t id);  /* d3_gen_patch_276.py */\n'),
 # 10. the main menu's entry labels by id (main+0x35bbe0): d3_menu.c d3_menu_label_id (Exit Game: ids shift)
 ('void f_700035bbe0(Cpu *c) {\n    FN_ENTER(0x700035bbe0ull);\n',
  '    c->x[0] = d3_menu_label_id((uint32_t)c->x[0]);  /* d3_gen_patch_276.py */\n',
  'uint32_t d3_menu_label_id(uint32_t id);  /* d3_gen_patch_276.py */\n'),
 # 6. the game's "UI sound by number" (main+0x4e5e50): D3_LOG_UI_SOUNDS logs each (d3_menu.c d3_ui_sound_seen)
 ('void f_70004e5e50(Cpu *c) {\n    FN_ENTER(0x70004e5e50ull);\n',
  '    d3_ui_sound_seen((uint32_t)c->x[0]);  /* d3_gen_patch_276.py */\n',
  'void d3_ui_sound_seen(uint32_t id);  /* d3_gen_patch_276.py */\n'),
 # 7. "play this sound" (main+0x315e10): D3_LOG_UI_SOUNDS logs each (d3_menu.c d3_ui_play_seen)
 ('void f_7000315e10(Cpu *c) {\n    FN_ENTER(0x7000315e10ull);\n',
  '    d3_ui_play_seen((uint32_t)c->x[0], c->x[30]);  /* d3_gen_patch_276.py */\n',
  'void d3_ui_play_seen(uint32_t snd, uint64_t lr);  /* d3_gen_patch_276.py */\n'),
 # 8. FMOD ChannelGroup::setVolume (main+0xa4d620): the game's "Music" group gets Music volume x the game's value
 #    (runtime/hle/d3_volume.c d3_group_volume)
 ('void f_7000a4d620(Cpu *c) {\n    FN_ENTER(0x7000a4d620ull);\n',
  '    d3_group_volume(c);  /* d3_gen_patch_276.py */\n',
  'void d3_group_volume(Cpu *c);  /* d3_gen_patch_276.py */\n'),
 # 4. zlib 1.2.3's inner decode loop (inflate_fast, main+0x12590): the host's version (runtime/hle/d3_inflate.c)
 ('void f_7000012590(Cpu *c) {\n    FN_ENTER(0x7000012590ull);\n',
  '    if (d3_inflate_fast(c)) return;  /* d3_gen_patch_276.py */\n',
  '_Bool d3_inflate_fast(Cpu *c); void d3_inflate_check(Cpu *c);  /* d3_gen_patch_276.py */\n'),
]

# 格式: (old_text, new_text, declaration)
REPLACES = [
 # 16. the world (game simulation) thread's sleep between its steps (main+0x7c5bdc): above 60 fps it waits for the
 #     next frame in which the game counts a step (hle/d3_clock.c d3_sim_wait)
 ('    c->x[0] = (uint32_t)((uint32_t)c->x[21] - (uint32_t)c->x[8]);\n    c->x[30] = 0x70007c5be0ull; f_7000006fb0(c);\nL_70007c5be0:;\n',
  '    c->x[0] = (uint32_t)((uint32_t)c->x[21] - (uint32_t)c->x[8]);\n    c->x[30] = 0x70007c5be0ull; if (!d3_sim_wait((uint32_t)c->x[0])) f_7000006fb0(c);  /* d3_gen_patch_276.py */\nL_70007c5be0:;\n',
  'int d3_sim_wait(uint32_t ms);  /* d3_gen_patch_276.py */\n'),
 # 15. THE 120 FPS FIX: the time the game hands its frame function (main+0x4c8790 -> main+0x40810) is ours above
 #     60 fps (hle/d3_clock.c d3_frame_time; the game's own smoothed frame clock can settle on every second frame)
 ('L_70004c8790:;\n    c->x[0] = (uint32_t)(0u | (uint32_t)c->x[19]);\n    c->x[30] = 0x70004c8798ull; f_7000040810(c);\n',
  'L_70004c8790:;\n    { uint64_t t_ = c->x[19]; c->x[30] = 0x70004c8794ull; f_7000a49b30(c); c->x[19] = d3_frame_time((uint32_t)t_, (uint32_t)c->x[0], c->x[21]); }  /* d3_gen_patch_276.py */\n    c->x[0] = (uint32_t)(0u | (uint32_t)c->x[19]);\n    c->x[30] = 0x70004c8798ull; f_7000040810(c);\n',
  'uint32_t d3_frame_time(uint32_t game_t, uint32_t now, uint64_t game);  /* d3_gen_patch_276.py */\n'),
 # 12. the world thread's sleep between its steps (main+0x4c63ac): above 60 fps it waits for its place in the
 #     frame slots instead (hle/d3_clock.c d3_world_wait)
 ('L_70004c63ac:;\n    c->x[30] = 0x70004c63b0ull; f_7000006fb0(c);\n',
  'L_70004c63ac:;\n    c->x[30] = 0x70004c63b0ull; if (!d3_world_wait((uint32_t)c->x[0])) f_7000006fb0(c);  /* d3_gen_patch_276.py */\n',
  'int d3_world_wait(uint32_t ms);  /* d3_gen_patch_276.py */\n'),
 # 2. the "Disconnected from Diablo Network / Not Signed In" box
 ('    c->x[1] = (uint32_t)(0u | 0x1ull);\n    c->pc = c->x[8]; c->x[30] = 0x7000362798ull; rt_dispatch(c);\n',
  '    c->x[1] = (uint32_t)(d3_online_status_shown());  /* d3_gen_patch_276.py */\n    c->pc = c->x[8]; c->x[30] = 0x7000362798ull; rt_dispatch(c);\n',
  'int d3_online_status_shown(void);  /* d3_gen_patch_276.py */\n'),
 ('    c->x[1] = (uint32_t)(0u | 0x1ull);\n    c->pc = c->x[8]; c->x[30] = 0x70002212b8ull; rt_dispatch(c);\n',
  '    c->x[1] = (uint32_t)(d3_online_status_shown());  /* d3_gen_patch_276.py */\n    c->pc = c->x[8]; c->x[30] = 0x70002212b8ull; rt_dispatch(c);\n',
  'int d3_online_status_shown(void);  /* d3_gen_patch_276.py */\n'),
 # 2b. the season status line ("Not Signed In" with the leaf) of the main menu
 ('    c->x[1] = (uint32_t)(0u | 0x1ull);\n    c->pc = c->x[8]; c->x[30] = 0x700036291cull; rt_dispatch(c);\n',
  '    c->x[1] = (uint32_t)(d3_online_status_shown());  /* d3_gen_patch_276.py */\n    c->pc = c->x[8]; c->x[30] = 0x700036291cull; rt_dispatch(c);\n',
  'int d3_online_status_shown(void);  /* d3_gen_patch_276.py */\n'),
 ('    c->x[1] = (uint32_t)(0u | 0x1ull);\n    c->pc = c->x[8]; c->x[30] = 0x7000362bfcull; rt_dispatch(c);\n',
  '    c->x[1] = (uint32_t)(d3_online_status_shown());  /* d3_gen_patch_276.py */\n    c->pc = c->x[8]; c->x[30] = 0x7000362bfcull; rt_dispatch(c);\n',
  'int d3_online_status_shown(void);  /* d3_gen_patch_276.py */\n'),
 ('    c->x[1] = (uint32_t)((uint32_t)c->x[19] & (uint32_t)c->x[8]);\n'
  '    { uint64_t ea = c->x[0] + 0x0ull; uint64_t v = LD64(ea); c->x[8] = (uint64_t)(v); }\n'
  '    { uint64_t ea = c->x[8] + 0x50ull; uint64_t v = LD64(ea); c->x[8] = (uint64_t)(v); }\n'
  '    c->pc = c->x[8]; c->x[30] = 0x7000362c30ull; rt_dispatch(c);\n',
  '    c->x[1] = (uint32_t)((uint32_t)c->x[19] & (uint32_t)c->x[8] & (uint32_t)d3_online_status_shown());  /* d3_gen_patch_276.py */\n'
  '    { uint64_t ea = c->x[0] + 0x0ull; uint64_t v = LD64(ea); c->x[8] = (uint64_t)(v); }\n'
  '    { uint64_t ea = c->x[8] + 0x50ull; uint64_t v = LD64(ea); c->x[8] = (uint64_t)(v); }\n'
  '    c->pc = c->x[8]; c->x[30] = 0x7000362c30ull; rt_dispatch(c);\n',
  'int d3_online_status_shown(void);  /* d3_gen_patch_276.py */\n'),
 # 2c. the season status box itself (SeasonStateNotification, handle main+0x1151210): SetVisible at main+0x3605b8
 ('    c->x[1] = (uint32_t)(0u | (uint32_t)c->x[20]);\n    c->pc = c->x[8]; c->x[30] = 0x70003605bcull; rt_dispatch(c);\n',
  '    c->x[1] = (uint32_t)(0u | ((uint32_t)c->x[20] & (uint32_t)d3_online_status_shown()));  /* d3_gen_patch_276.py */\n'
  '    c->pc = c->x[8]; c->x[30] = 0x70003605bcull; rt_dispatch(c);\n',
  'int d3_online_status_shown(void);  /* d3_gen_patch_276.py */\n'),
 # 2d. Pause-menu option calls are handled semantically by apply_pause_menu_patches().
] + [
  # 2e. pause menu's button hint "View Online Friends"
  ('    c->x[30] = 0x700022120cull; f_70001bb550(c);\n',
   '    if (d3_options_tab_shown(4)) { c->x[30] = 0x700022120cull; f_70001bb550(c); }  /* d3_gen_patch_276.py */\n',
   'int d3_options_tab_shown(int which);  /* d3_gen_patch_276.py */\n'),
  # 4b. the end of that loop: D3_INFLATE_CHECK=1 compares the host's result with the lifted one
  ('    c->sp = (uint64_t)(c->sp + 0xa0ull);\n    return;\n    rt_udf(c, 0x7000012d48ull);\n',
   '    c->sp = (uint64_t)(c->sp + 0xa0ull);\n    d3_inflate_check(c);  /* d3_gen_patch_276.py */\n    return;\n'
   '    rt_udf(c, 0x7000012d48ull);\n',
   '_Bool d3_inflate_fast(Cpu *c); void d3_inflate_check(Cpu *c);  /* d3_gen_patch_276.py */\n'),
  # 3. Options tabs: Multiplayer and Privacy
  ('    c->x[30] = 0x700020e24cull; f_7000210450(c);\n',
   '    if (d3_options_tab_shown(1)) { c->x[30] = 0x700020e24cull; f_7000210450(c); }  /* d3_gen_patch_276.py */\n',
   'int d3_options_tab_shown(int which);  /* d3_gen_patch_276.py */\n'),
  ('    c->x[30] = 0x700020e26cull; f_7000210450(c);\n',
   '    if (d3_options_tab_shown(2)) { c->x[30] = 0x700020e26cull; f_7000210450(c); }  /* d3_gen_patch_276.py */\n',
   'int d3_options_tab_shown(int which);  /* d3_gen_patch_276.py */\n'),
 ]

# Map-hint calls are handled semantically by apply_map_hint_patches().

# 格式: (old_text, new_text) - Earlier versions of a patch's text, brought up to date first
# Always run on freshly generated 2.7.6 C files. The main() preflight refuses legacy 2.7.7-patched files.
UPGRADES = []

SEASON_DECL = 'int d3_offline_season_num(void);  /* d3_gen_patch_276.py */\n'

SEASON_RULES = [
 # 1. IsSignedInOnline (main+0x56b10)
 ('IsSignedInOnline',
  'void f_7000056b10(Cpu *c) {',
  r'(void f_7000056b10\(Cpu \*c\) \{\n(?:    FN_ENTER[^\n]*\n)?)',
  r'\1    if (d3_offline_season_num() > 0) { c->x[0] = 1; return; }  /* d3_gen_patch_276.py */\n'),

 # 2. ValidateHeroForPartyMember (main+0x1bf5f0)
 ('ValidateHeroForPartyMember',
  'void f_70001bf5f0(Cpu *c) {',
  r'(void f_70001bf5f0\(Cpu \*c\) \{\n(?:    FN_ENTER[^\n]*\n)?)',
  r'\1    if (d3_offline_season_num() > 0) { c->x[0] = 0; return; }  /* d3_gen_patch_276.py */\n'),

 # 3. IsSeasonsInitialized (main+0x5ff0c: and w0, w8, #1)
 ('IsSeasonsInitialized',
  'L_700005ff0c:',
  r'(L_700005ff0c:;\n)([^\n]+\n)',
  r'\1    if (d3_offline_season_num() > 0) { c->x[0] = 1; } else { \2    }  /* d3_gen_patch_276.py */\n'),

 # 4. 创建赛季角色确认回调：2.7.6 的 0x351CBC 是函数 f_7000351cb0 内的条件跳转指令，
 # 生成 C 不一定会为该指令单独输出 L_7000351cbc 标签，因此按实际条件跳转语句匹配。
 # 赛季开启时设置 x1=1 并跳过原分支；赛季关闭时保留原始 COND_NE 分支。
 ('SeasonConfirmCallback',
  'void f_7000351cb0(Cpu *c) {',
  r'(?s)(void f_7000351cb0\(Cpu \*c\) \{.*?)(?m:^(?P<indent>[ \t]*)if \(COND_NE\(c\)\) \{ goto L_7000351cec; \})',
  r'\1\g<indent>if (d3_offline_season_num() > 0) { c->x[1] = 1; } else if (COND_NE(c)) { goto L_7000351cec; }  /* d3_gen_patch_276.py */'),

 # 5. SetGameParamsForHero (main+0x1bd140)
 ('SetGameParamsForHero',
  'L_70001bd140:',
  r'(L_70001bd140:;\n)([^\n]+\n)',
  r'\1    if (d3_offline_season_num() > 0) { c->x[21] = (uint32_t)d3_offline_season_num(); } else { \2    }  /* d3_gen_patch_276.py */\n'),

 # 6. 赛季在线服务状态检查 (main+0x72dfa0)
 ('SeasonServiceAvailable',
  'void f_700072dfa0(Cpu *c) {',
  r'(void f_700072dfa0\(Cpu \*c\) \{\n(?:    FN_ENTER[^\n]*\n)?)',
  r'\1    if (d3_offline_season_num() > 0) { c->x[0] = 1; return; }  /* d3_gen_patch_276.py */\n'),

 # 7. GetSeasonNum (main+0x72df90)
 ('GetSeasonNum',
  'void f_700072df90(Cpu *c) {',
  r'(void f_700072df90\(Cpu \*c\) \{\n(?:    FN_ENTER[^\n]*\n)?)',
  r'\1    if (d3_offline_season_num() > 0) { c->x[0] = (uint32_t)d3_offline_season_num(); return; }  /* d3_gen_patch_276.py */\n'),

 # 8. 解锁赛季道具掉落权。对应 2.7.6 金手指：0x492EF0 = 0x14000005，B 到 0x492F04。
 # 开启离线赛季时执行同等跳转，未开启时保留原逻辑。
 ('SeasonDropUnlock1',
  'L_7000492ef0:;',
  r'(L_7000492ef0:;\n)',
  r'\1    if (d3_offline_season_num() > 0) { goto L_7000492f04; }  /* d3_gen_patch_276.py */\n'),

 # 9. 解锁赛季道具掉落权。对应 2.7.6 金手指：
 #    0x897888 = 0x52800020 (MOV W0, #1)，0x89788C = 0x1400001A (B 到 0x8978F4)。
 # 开启离线赛季时返回 1 并跳过资格检查，未开启时执行原 helper。
 ('SeasonDropUnlock2',
  'c->x[30] = 0x700089788cull; f_700050e700(c);',
  r'(    c->x\[30\] = 0x700089788cull; f_700050e700\(c\);\n)',
  r'    if (d3_offline_season_num() > 0) { c->x[0] = 1; goto L_70008978f4; }  /* d3_gen_patch_276.py */\n\1'),
]


def _add_decl(s, decl):
 if not decl or decl in s:
  return s
 idx = s.find('#include "simd.h"')
 if idx != -1:
  i = s.index('\n', idx) + 1
  return s[:i] + decl + s[i:]
 return s


def _generated_function_region(s, pos):
 """Return (start, end) for the generated f_<addr>(Cpu *c) containing pos."""
 starts = list(re.finditer(r'^void f_[0-9a-fA-F]+\(Cpu \*c\) \{$', s, re.MULTILINE))
 current = None
 next_start = len(s)
 for m in starts:
  if m.start() <= pos:
   current = m.start()
  elif current is not None:
   next_start = m.start()
   break
 if current is None:
  return None
 return current, next_start


def validate_season_drop_targets(fn, s):
 """Fail early rather than emit a C goto whose target label is missing/outside its function."""
 checks = (
  ('SeasonDropUnlock1', 'L_7000492ef0:;', 'L_7000492f04:;'),
  ('SeasonDropUnlock2', 'c->x[30] = 0x700089788cull; f_700050e700(c);', 'L_70008978f4:;'),
 )
 for name, source_probe, target_label in checks:
  tag = f'/* d3_gen_patch_276.py: {name} */'
  if tag not in s:
   continue
  pos = s.find(tag)
  region = _generated_function_region(s, pos)
  if region is None:
   raise SystemExit(f'd3_gen_patch_276: {fn}: {name}: cannot determine generated function containing patch')
  start, end = region
  if target_label not in s[start:end]:
   raise SystemExit(
    f'd3_gen_patch_276: {fn}: {name}: target label {target_label} is missing from the same generated function. '
    'Do not compile this output yet; the generator may need to emit this branch target as a label.'
   )
 return s


def apply_season_patches(fn, s, hit_stats=None):
 changed = False
 for idx, (name, probe, pat, repl) in enumerate(SEASON_RULES):
  tag = f'/* d3_gen_patch_276.py: {name} */'
  if tag in s:
   if hit_stats is not None:
    hit_stats['season'][idx] += 1
   continue
  if probe not in s:
   continue
  s_new, n = re.subn(pat, repl.replace('/* d3_gen_patch_276.py */', tag), s, count=1)
  if n != 1:
   pos = s.find(probe)
   snippet = s[max(0, pos - 60):pos + 220].replace('\n', '\\n')
   raise SystemExit(f'd3_gen_patch: {fn}: {name} matched {n} times. Context: {snippet}')
  s = s_new
  changed = True
  if hit_stats is not None:
   hit_stats['season'][idx] += 1
 if changed:
  s = _add_decl(s, SEASON_DECL)
 # The cheat-derived branches must land on labels within the same generated function.
 s = validate_season_drop_targets(fn, s)
 return s



PAUSE_TAB_DECL = 'int d3_options_tab_shown(int which);  /* d3_gen_patch_276.py */\n'
MAP_HINT_DECL = 'int d3_map_zoom_hints(void);  /* d3_gen_patch_276.py */\n'


def apply_pause_menu_patches(fn, s, hit_stats=None):
 """Hide pause-menu option calls by call target + address region, not fragile exact LR addresses.

The 2.7.7 -> 2.7.6 signature report missed some internal instructions around these calls,
so this matches only calls to the known pause helper whose return addresses fall in 0x21f500..0x21f800.
 """
 pattern = re.compile(
  r'^(?P<indent>[ \t]*)c->x\[30\] = (?P<lr>0x[0-9a-fA-F]+ull); f_700021f780\(c\);$',
  re.MULTILINE)
 tag = '/* d3_gen_patch_276.py: pause tab */'

 def repl(m):
  try:
   address = int(m.group('lr')[:-3], 16)  # strip trailing 'ull'
  except ValueError:
   return m.group(0)
  if not (0x700021f500 <= address <= 0x700021f800):
   return m.group(0)
  return (f"{m.group('indent')}if (d3_options_tab_shown(3)) {{ "
          f"c->x[30] = {m.group('lr')}; f_700021f780(c); }}  {tag}")

 s, _ = pattern.subn(repl, s)
 # Count tags in this source chunk so repeat runs remain idempotent and diagnostics are meaningful.
 if hit_stats is not None:
  hit_stats['pause_menu'] += s.count(tag)
 if tag in s:
  s = _add_decl(s, PAUSE_TAB_DECL)
 return s


def apply_map_hint_patches(fn, s, hit_stats=None):
 """Patch map-button hint calls within the matched 2.7.6 map-hint handler function.

Internal call-site signatures were not uniquely found by the address scanner. The handler entry,
however, matched exactly at 0x3e7250, so limit semantic matching to that function.
 """
 signature = 'void f_70003e7250(Cpu *c) {'
 start = s.find(signature)
 if start < 0:
  return s
 end = s.find('\n}', start + len(signature))
 if end < 0:
  print(f'd3_gen_patch_276: {fn}: could not find end of map-hint handler')
  return s
 body = s[start:end]
 pattern = re.compile(
  r'^(?P<indent>[ \t]*)c->x\[30\] = (?P<lr>0x[0-9a-fA-F]+ull); f_70001bb550\(c\);$',
  re.MULTILINE)
 tag = '/* d3_gen_patch_276.py: map hint */'

 def repl(m):
  return (f"{m.group('indent')}if (d3_map_zoom_hints()) {{ "
          f"c->x[30] = {m.group('lr')}; f_70001bb550(c); }}  {tag}")

 new_body, _ = pattern.subn(repl, body)
 if new_body != body:
  s = s[:start] + new_body + s[end:]
  s = _add_decl(s, MAP_HINT_DECL)
 if hit_stats is not None:
  # Count inserted-or-existing tags in this function only.
  latest_start = s.find(signature)
  latest_end = s.find('\n}', latest_start + len(signature)) if latest_start >= 0 else -1
  if latest_start >= 0 and latest_end >= 0:
   hit_stats['map_hints'] += s[latest_start:latest_end].count(tag)
 return s


def apply_text(fn, s, hit_stats=None):
 """The patched text of any generated chunk file `fn`, matched purely by code patterns."""
 # 1. 升级旧版本补丁
 for old, new in UPGRADES:
  if old in s:
   s = s.replace(old, new)

 # 2. 插入型补丁 (PATCHES)
 for idx, (anchor, insert, decl) in enumerate(PATCHES):
  if insert in s:
   if hit_stats is not None:
    hit_stats['patches'][idx] += 1
   continue
  if anchor not in s:
   continue
  if s.count(anchor) != 1:
   raise SystemExit(f'd3_gen_patch: {fn}: anchor matched multiple times: {anchor.strip()}')
  s = _add_decl(s.replace(anchor, anchor + insert, 1), decl)
  if hit_stats is not None:
   hit_stats['patches'][idx] += 1

 # 3. 替换型补丁 (REPLACES)
 for idx, (old, new, decl) in enumerate(REPLACES):
  if new in s:
   if hit_stats is not None:
    hit_stats['replaces'][idx] += 1
   continue
  if old not in s:
   continue
  if s.count(old) != 1:
   raise SystemExit(f'd3_gen_patch: {fn}: replace target matched multiple times: {old.strip()}')
  s = _add_decl(s.replace(old, new, 1), decl)
  if hit_stats is not None:
   hit_stats['replaces'][idx] += 1

 # 3b. Address-signature misses handled semantically using confirmed 2.7.6 function entries.
 s = apply_pause_menu_patches(fn, s, hit_stats)
 s = apply_map_hint_patches(fn, s, hit_stats)

 # 4. 赛季与金手指补丁
 s = apply_season_patches(fn, s, hit_stats)
 s = apply_cheat_patches(fn, s)
 return s


def main():
 os.makedirs(BACKUP, exist_ok=True)
 c_files = sorted(glob.glob(os.path.join(GEN, 'main_*.c')))
 if not c_files:
  print(f'No main_*.c files found in {GEN}')
  return

 hit_stats = {
  'patches': [0] * len(PATCHES),
  'replaces': [0] * len(REPLACES),
  'season': [0] * len(SEASON_RULES),
  'pause_menu': 0,
  'map_hints': 0,
 }

 modified_files = []
 for p in c_files:
  fn = os.path.basename(p)
  orig_s = open(p, encoding='utf-8').read()
  if '/* d3_gen_patch.py' in orig_s:
   print(f'{fn}: SKIPPED: legacy d3_gen_patch.py markers found. Regenerate the 2.7.6 C files before using d3_gen_patch_276.py.')
   continue
  new_s = apply_text(fn, orig_s, hit_stats)

  if new_s != orig_s:
   b = os.path.join(BACKUP, fn + '.orig')
   if not os.path.exists(b):
    shutil.copyfile(p, b)
   open(p, 'w', encoding='utf-8', newline='\n').write(new_s)
   modified_files.append(fn)
   print(f'{fn}: patched')

 if not modified_files:
  print('All files are already up to date.')
 else:
  print(f'Total files patched: {len(modified_files)}')

 # 全局检查：报告在所有 main_*.c 中都未命中的规则，防止重新生成代码后静默失效
 for idx, count in enumerate(hit_stats['patches']):
  if count == 0:
   print(f'WARNING: PATCHES[{idx}] did not match any file: {PATCHES[idx][0].strip()}')
 for idx, count in enumerate(hit_stats['replaces']):
  if count == 0:
   first_line = REPLACES[idx][0].strip().splitlines()[0]
   print(f'WARNING: REPLACES[{idx}] did not match any file: {first_line}')
 for idx, count in enumerate(hit_stats['season']):
  if count == 0:
   print(f'WARNING: SEASON_RULES[{idx}] ({SEASON_RULES[idx][0]}) did not match any file.')
 # SEASON_RULES indices 7 and 8 are the two cheat-derived season-drop patches.
 for idx in (7, 8):
  status = 'matched' if hit_stats['season'][idx] else 'NOT MATCHED'
  print(f"[season-drop] {SEASON_RULES[idx][0]}: {status}; source cheat offset(s): "
        + ('0x492EF0 -> 0x492F04' if idx == 7 else '0x897888 / 0x89788C -> 0x8978F4'))
 if hit_stats['pause_menu'] != 5:
  print(f"WARNING: pause-menu semantic patch matched {hit_stats['pause_menu']} call(s); expected 5. Verify the 2.7.6 generated C.")
 if hit_stats['map_hints'] != 4:
  print(f"WARNING: map-hint semantic patch matched {hit_stats['map_hints']} call(s); expected 4. Verify the 2.7.6 map-hint handler.")

 if sys.stdin and sys.stdin.isatty():
  try:
   input('Press Enter to close...')
  except EOFError:
   pass


# ---- Local game build: auto-load cheats/*.txt next to lasrecomp.exe ----
def _find_cheats_dir():
 # Preserve the original d3_gen_patch.py directory search; do not create or
 # switch to a separate cheats_276 directory.
 exe_dir = os.path.dirname(os.path.abspath(sys.executable))
 candidates = [
  os.path.join(os.getcwd(), 'cheats'),
  os.path.join(exe_dir, 'cheats'),
  os.path.abspath(os.path.join(exe_dir, '..', 'cheats')),
  os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'cheats')),
 ]
 for d in candidates:
  if os.path.isdir(d):
   return d
 return None

def _build_cheat_table():
 cheats_dir = _find_cheats_dir()
 if not cheats_dir:
  print('[d3_cheats] cheats/ not found; skipping cheat loading')
  return []
 entries = []
 seen = set()
 for fname in sorted(os.listdir(cheats_dir)):
  if not fname.lower().endswith('.txt'):
   continue
  cur_name, cur_ops = None, []
  with open(os.path.join(cheats_dir, fname), encoding='utf-8', errors='ignore') as f:
   for raw in f:
    line = raw.strip()
    if not line:
     continue
    if line.startswith('[') and line.endswith(']'):
     if cur_name and cur_ops and cur_name not in seen:
      seen.add(cur_name)
      entries.append((cur_name, cur_ops))
     cur_name = line[1:-1].lstrip('►★ ').strip()
     cur_ops = []
    elif cur_name:
     parts = line.split()
     if len(parts) == 3:
      op_type, op_off, op_val = parts
      if op_type.upper() == '04000000':
       try:
        cur_ops.append((int(op_off, 16), int(op_val, 16)))
       except ValueError:
        pass
  if cur_name and cur_ops and cur_name not in seen:
   seen.add(cur_name)
   entries.append((cur_name, cur_ops))

 rules = []
 used_vas = set()
 cid = 0
 try:
  from lifter import Lifter, emit_asm_batch, hx
  lft = Lifter(0x7000000000, 'c')
  for name, ops in entries:
   if any(off >= 0xC70000 or (0x7000000000 + off) in used_vas for off, _ in ops):
    continue
   lifted = []
   ok = True
   for off, word in ops:
    va = 0x7000000000 + off
    ins = lft.lift(word, va)
    k = ins.kind
    if k == 'op':
     code = ins.code
    elif k == 'asm':
     code = emit_asm_batch([ins.asm])
    elif k == 'ret':
     code = 'return;'
    elif k == 'b':
     code = f'goto L_{ins.target:x};'
    elif k == 'bcond':
     code = f'if ({ins.cond}) {{ goto L_{ins.target:x}; }}'
    elif k == 'bl':
     code = f'c->x[30] = {hx(va + 4)}; f_{ins.target:x}(c);'
    else:
     ok = False
     break
    if not code or 'rt_udf' in code:
     ok = False
     break
    lifted.append((va, code))
   if ok and lifted:
    for va, code in lifted:
     used_vas.add(va)
     rules.append((cid, name, va, code))
    cid += 1
 except Exception as e:
  print(f'[d3_cheats] error: {e}')
 print(f'[d3_cheats] loaded {cid} cheats from {cheats_dir}')
 return rules


CHEAT_DECL = 'int d3_cheat_on(int id);  /* d3_gen_patch_276.py */\n'
CHEAT_RULES = _build_cheat_table()


def apply_cheat_patches(fn, s):
 if not CHEAT_RULES:
  return s
 changed = False
 for cid, name, va, c_code in CHEAT_RULES:
  lbl = f'L_{va:x}:;'
  tag = f'/* cheat:{cid}:{va:x} */'
  if lbl not in s or tag in s:
   continue
  # 若新指令包含 goto L_xxx; 且目标标签未在当前文件中生成，则安全跳过该条（不改动 gen.py，零编译风险）
  m_goto = re.search(r'goto (L_[0-9a-f]+);', c_code)
  if m_goto and f'{m_goto.group(1)}:' not in s:
   continue
  pat = re.compile(rf'({re.escape(lbl)}\n)(.*?)(\n(?:\s*L_[0-9a-f]+:;|\}}))', re.DOTALL)

  def repl_fn(m):
   orig = m.group(2).strip()
   return f'{m.group(1)}    if (d3_cheat_on({cid})) {{ {c_code} }} else {{ {orig} }}  {tag}{m.group(3)}'

  s_new, n = pat.subn(repl_fn, s, count=1)
  if n == 1:
   s = s_new
   changed = True
 if changed:
  s = _add_decl(s, CHEAT_DECL)
 return s


if __name__ == '__main__':
 main()
 