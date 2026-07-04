// pybind11 glue - exposes the automaton to python as ac_engine.Scanner
//
//   from ac_engine import Scanner
//   s = Scanner(["ignore previous instructions", "system prompt"])
//   s.scan("please ignore previous instructions")
//   -> [(0, 7, 36)]   # (pattern_id, start, end)
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <string>
#include <tuple>
#include <vector>

#include "aho_corasick.hpp"

namespace py = pybind11;

namespace {

// thin wrapper, immutable after ctor. automaton sits behind it so python holds
// one cheap-to-share obj.
class Scanner {
public:
    explicit Scanner(const std::vector<std::string>& patterns) {
        for (std::size_t i = 0; i < patterns.size(); ++i) {
            automaton_.add(patterns[i], static_cast<int>(i));
        }
        automaton_.build();
    }

    // (pattern_id, start, end) per hit. drop the gil for the scan itself, no
    // python state touched in there.
    std::vector<std::tuple<int, std::size_t, std::size_t>> scan(
        const std::string& text) const {
        std::vector<acengine::Match> raw;
        {
            py::gil_scoped_release release;
            raw = automaton_.search(text);
        }
        std::vector<std::tuple<int, std::size_t, std::size_t>> out;
        out.reserve(raw.size());
        for (const auto& m : raw) {
            out.emplace_back(m.pattern_id, m.start, m.end);
        }
        return out;
    }

    std::size_t pattern_count() const { return automaton_.pattern_count(); }

private:
    acengine::Automaton automaton_;
};

}  // namespace

PYBIND11_MODULE(ac_engine, m) {
    m.doc() = "aho-corasick multi-pattern scanner (c++ core)";

    py::class_<Scanner>(m, "Scanner")
        .def(py::init<const std::vector<std::string>&>(), py::arg("patterns"),
             "build from a list of patterns (case-insensitive). pattern id in "
             "results == list index.")
        .def("scan", &Scanner::scan, py::arg("text"),
             "scan text, return list of (pattern_id, start, end)")
        .def_property_readonly("pattern_count", &Scanner::pattern_count,
                               "how many patterns are loaded");
}
