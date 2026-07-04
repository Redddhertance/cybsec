// aho-corasick multi-pattern matcher.
// build one automaton from N patterns, then one linear pass over the input
// spits out every hit (overlaps included). built once at startup, after that
// it's read-only so many reqs can hit it at once.
#pragma once

#include <cstdint>
#include <string>
#include <unordered_map>
#include <vector>

namespace acengine {

// one hit. start/end = byte offsets into the lowercased input, span is
// [start,end). pattern_id indexes the pattern list we built from.
struct Match {
    int pattern_id;
    std::size_t start;
    std::size_t end;
};

class Automaton {
public:
    Automaton() { new_node(); }  // node 0 = root

    // add a pattern. case-insensitive so we lowercase on insert. empties
    // ignored. call before build().
    void add(const std::string& pattern, int pattern_id);

    // finalise: fail links + output propagation. call once, after all add()s
    // and before any search().
    void build();

    // scan text, return every hit. thread-safe once built (nothing mutable
    // gets touched). lowercased internally = case-insensitive.
    std::vector<Match> search(const std::string& text) const;

    std::size_t pattern_count() const { return pattern_lengths_.size(); }

private:
    struct Node {
        std::unordered_map<unsigned char, int> next;  // goto edges
        int fail = 0;                                  // fail link
        // pattern ids ending exactly here (pre output-merge)
        std::vector<int> outputs;
        // after build(): next node up the dict-suffix chain, or -1
        int output_link = -1;
    };

    int new_node();

    std::vector<Node> nodes_;
    std::vector<std::size_t> pattern_lengths_;  // indexed by pattern_id
    bool built_ = false;
};

}  // namespace acengine
