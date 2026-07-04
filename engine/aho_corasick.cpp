#include "aho_corasick.hpp"
#include <algorithm>
#include <cctype>
#include <queue>

namespace acengine {

namespace {
inline unsigned char lower(unsigned char c) {
    return static_cast<unsigned char>(std::tolower(c));
}
} 

int Automaton::new_node() {
    nodes_.emplace_back();
    return static_cast<int>(nodes_.size()) - 1;
}

void Automaton::add(const std::string& pattern, int pattern_id) {
    if (pattern.empty()) {
        return;
    }
    if (static_cast<std::size_t>(pattern_id) >= pattern_lengths_.size()) {
        pattern_lengths_.resize(pattern_id + 1, 0);
    }
    pattern_lengths_[pattern_id] = pattern.size();

    int node = 0;
    for (char ch : pattern) {
        unsigned char c = lower(static_cast<unsigned char>(ch));
        auto it = nodes_[node].next.find(c);
        if (it == nodes_[node].next.end()) {
            int created = new_node();
            //fetch again, new_node() may have reallocated the vector.
            nodes_[node].next[c] = created;
            node = created;
        } else {
            node = it->second;
        }
    }
    nodes_[node].outputs.push_back(pattern_id);
}

void Automaton::build() {
    // bfs instead of depth1 nodes first; their failure link is always the root.
    std::queue<int> q;
    for (auto& [c, child] : nodes_[0].next) {
        nodes_[child].fail = 0;
        q.push(child);
    }

    while (!q.empty()) {
        int node = q.front();
        q.pop();

        // compute  dictionary-suffix  once  so search() can walk it directly (instead of pursuing fail w no output)
        int f = nodes_[node].fail;
        nodes_[node].output_link =
            !nodes_[f].outputs.empty() ? f : nodes_[f].output_link;

        for (auto& [c, child] : nodes_[node].next) {
            // child fail = goto(fail(node), c). walk fail links til theres an edge on c, else drop to root
            int f2 = nodes_[node].fail;
            while (f2 != 0 && nodes_[f2].next.find(c) == nodes_[f2].next.end()) {
                f2 = nodes_[f2].fail;
            }
            auto it = nodes_[f2].next.find(c);
            nodes_[child].fail =
                (it != nodes_[f2].next.end() && it->second != child) ? it->second : 0;
            q.push(child);
        }
    }
    built_ = true;
}

std::vector<Match> Automaton::search(const std::string& text) const {
    std::vector<Match> matches;
    if (!built_) {
        return matches;
    }

    int node = 0;
    for (std::size_t i = 0; i < text.size(); ++i) {
        unsigned char c = lower(static_cast<unsigned char>(text[i]));

        // follow fail links til we can eat c (or hit root)
        while (node != 0 && nodes_[node].next.find(c) == nodes_[node].next.end()) {
            node = nodes_[node].fail;
        }
        auto it = nodes_[node].next.find(c);
        if (it != nodes_[node].next.end()) {
            node = it->second;
        }

        // emit whatever ends here, then walk the dict-suffix chain
        std::size_t end = i + 1;
        for (int v = node; v != -1; v = nodes_[v].output_link) {
            for (int pid : nodes_[v].outputs) {
                matches.push_back(Match{pid, end - pattern_lengths_[pid], end});
            }
        }
    }
    return matches;
}

}  // namespace acengine
