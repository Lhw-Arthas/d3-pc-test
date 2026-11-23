#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <string>
#include <vector>
#include <set>
#include <algorithm>
#include <filesystem>
#include <SDL3/SDL.h>
#include "imgui.h"
#include "option_rows.h"

namespace fs = std::filesystem;

struct D3CheatEntry {
    std::string name;
    bool enabled;
};

static std::vector<D3CheatEntry> g_cheats;
static bool g_cheats_loaded = false;

static std::string trim_str(const std::string &s) {
    size_t a = s.find_first_not_of(" \t\r\n");
    if (a == std::string::npos) return "";
    size_t b = s.find_last_not_of(" \t\r\n");
    return s.substr(a, b - a + 1);
}

static std::string strip_prefix(const std::string &s) {
    size_t i = 0;
    while (i < s.size()) {
        unsigned char c = (unsigned char)s[i];
        if (c == ' ' || c == '\t') { i++; continue; }
        if (i + 2 < s.size() && c == 0xE2 && (unsigned char)s[i+1] == 0x96 && (unsigned char)s[i+2] == 0xBA) { i += 3; continue; }
        if (i + 2 < s.size() && c == 0xE2 && (unsigned char)s[i+1] == 0x98 && (unsigned char)s[i+2] == 0x85) { i += 3; continue; }
        break;
    }
    return trim_str(s.substr(i));
}

static void d3_cheats_ensure_loaded(void) {
    if (g_cheats_loaded) return;
    g_cheats_loaded = true;
    std::error_code ec;
    fs::path dir = fs::path("cheats");
    if (!fs::exists(dir, ec)) {
        if (const char *base = SDL_GetBasePath()) dir = fs::path(base) / "cheats";
    }
    if (!fs::exists(dir, ec) || !fs::is_directory(dir, ec)) return;

    std::vector<fs::path> files;
    for (const auto &ent : fs::directory_iterator(dir, ec)) {
        std::string ext = ent.path().extension().string();
        std::transform(ext.begin(), ext.end(), ext.begin(), ::tolower);
        if (ent.is_regular_file() && ext == ".txt")
            files.push_back(ent.path());
    }
    std::sort(files.begin(), files.end());

    std::set<std::string> seen_names;
    std::set<uint32_t> used_offs;

    for (const auto &fp : files) {
        FILE *f = fopen(fp.string().c_str(), "rb");
        if (!f) continue;
        char buf;
        std::string cur_name;
        std::vector<uint32_t> cur_offs;
        bool valid = true;

        auto flush_entry = [&]() {
            if (!cur_name.empty() && !cur_offs.empty() && valid && !seen_names.count(cur_name)) {
                seen_names.insert(cur_name);
                for (uint32_t o : cur_offs) used_offs.insert(o);
                g_cheats.push_back({cur_name, false});
            }
            cur_name.clear();
            cur_offs.clear();
            valid = true;
        };

        while (fgets(buf, sizeof buf, f)) {
            std::string line = trim_str(buf);
            if (line.empty()) continue;
            if (line.front() == '[' && line.back() == ']') {
                flush_entry();
                cur_name = strip_prefix(line.substr(1, line.size() - 2));
            } else if (!cur_name.empty()) {
                unsigned int type = 0, off = 0, val = 0;
                if (sscanf(line.c_str(), "%x %x %x", &type, &off, &val) == 3 && type == 0x04000000u) {
                    if (off >= 0xC70000u || used_offs.count(off)) valid = false;
                    cur_offs.push_back(off);
                }
            }
        }
        flush_entry();
        fclose(f);
    }
}

extern "C" int d3_cheat_on(int id) {
    if (id < 0 || id >= (int)g_cheats.size()) return 0;
    return g_cheats[id].enabled ? 1 : 0;
}

extern "C" void d3_cheats_tab_draw(float scale) {
    d3_cheats_ensure_loaded();
    opt_begin("##d3cheats", scale);
    opt_section("Cheats (cheats/*.txt)");
    if (g_cheats.empty()) {
        ImGui::TextDisabled("No cheats found. Put Switch .txt files into the 'cheats' folder and rebuild game code.");
    } else {
        if (opt_action("Disable All Cheats", "", "Turns off every active cheat below.", false, false)) {
            for (auto &c : g_cheats) c.enabled = false;
        }
        for (size_t i = 0; i < g_cheats.size(); i++) {
            opt_toggle(g_cheats[i].name.c_str(), &g_cheats[i].enabled, false, "Toggle this cheat in real time.");
        }
    }
    opt_end();
}
