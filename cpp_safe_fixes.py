"""Preview-first, conservative C++17 safe-fix suggestions."""
from __future__ import annotations
import re

class CppSafeFixer:
    KNOWN_TYPO = {
        "coutt": "std::cout", "cnout": "std::cout", "std::coutt": "std::cout",
        "incldue": "include", "inlcude": "include", "retrun": "return",
    }
    HEADER_RULES = [
        (r"\b(?:std::)?(?:cout|cin|cerr)\b", "#include <iostream>"),
        (r"\bstring\b", "#include <string>"),
        (r"\bvector\b", "#include <vector>"),
        (r"\b(?:pow|sqrt|sin|cos|abs)\s*\(", "#include <cmath>"),
        (r"\b(?:sort|find|reverse)\s*\(", "#include <algorithm>"),
    ]
    def __init__(self, source: str):
        self.original = source or ""
        self.source = self.original

    @staticmethod
    def _replace_code_only(line, wrong, right):
        parts = re.split(r'("(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\')', line)
        for i in range(0, len(parts), 2):
            parts[i] = re.sub(r"\b" + re.escape(wrong) + r"\b", right, parts[i])
        return "".join(parts)

    def suggestions(self):
        lines = self.source.splitlines()
        fixes = []
        corrected = list(lines)
        # Correct only code segments, never comments or quoted string/char literals.
        for i, line in enumerate(lines, 1):
            if line.lstrip().startswith(("//", "/*", "*")):
                continue
            updated = line
            for wrong, right in self.KNOWN_TYPO.items():
                updated = self._replace_code_only(updated, wrong, right)
            # Qualify ordinary stream names to make fixes compilable.
            updated = self._replace_code_only(updated, "cout", "std::cout")
            updated = re.sub(r"(?<!std::)std::std::cout", "std::cout", updated)
            updated = self._replace_code_only(updated, "cin", "std::cin")
            updated = re.sub(r"(?<!std::)std::std::cin", "std::cin", updated)
            updated = self._replace_code_only(updated, "cerr", "std::cerr")
            updated = re.sub(r"(?<!std::)std::std::cerr", "std::cerr", updated)
            if updated != line:
                fixes.append((i, "Correct recognizable C++ stream/keyword typo", updated))
                corrected[i-1] = updated

        corrected_source = "\n".join(corrected)
        existing_headers = set(re.findall(r'^\s*#\s*include\s*[<"]([^>"]+)[>"]', corrected_source, re.M))
        required = []
        for pattern, header in self.HEADER_RULES:
            name = re.search(r"<([^>]+)>", header).group(1)
            if re.search(pattern, corrected_source) and name not in existing_headers and header not in required:
                required.append(header)
        if required:
            insert_at = max((i for i, row in enumerate(lines) if row.strip().startswith("#include")), default=-1) + 1
            fixes.append((insert_at + 1, "Insert missing standard header(s)", "\n".join(required)))

        # Detect missing semicolon for simple statements, after typo/qualification.
        for i, line in enumerate(corrected, 1):
            stripped = line.strip()
            if not stripped or stripped.startswith(("#", "//")) or stripped.endswith((";", "{", "}", ":")):
                continue
            if re.match(r"^(if|for|while|switch|else|do|class|struct|namespace|try|catch)\b", stripped):
                continue
            declaration = re.match(r"^(?:const\s+)?(?:int|long|short|float|double|char|bool|auto|std::string|string)\s+\w+\s*(?:=.*)?$", stripped)
            assignment = re.match(r"^[A-Za-z_]\w*(?:\.[\w]+|\[[^]]+\])*\s*(?:[+\-*/%]?=)\s*.+$", stripped)
            stream = re.match(r"^(?:std::)?(?:cout|cerr)\s*<<.+$", stripped)
            call = re.match(r"^[A-Za-z_]\w*\s*\(.+\)$", stripped)
            if declaration or assignment or stream or call:
                replacement = line.rstrip() + ";"
                existing = next((idx for idx, item in enumerate(fixes) if item[0] == i and not item[1].startswith("Insert missing")), None)
                if existing is None:
                    fixes.append((i, "Add missing semicolon to simple statement", replacement))
                else:
                    fixes[existing] = (i, fixes[existing][1] + "; Add missing semicolon", replacement)
                corrected[i-1] = replacement

        main = re.search(r"\bint\s+main\s*\([^)]*\)\s*\{", corrected_source)
        if main and not re.search(r"\breturn\s+\d+\s*;", corrected_source[main.end():]):
            close = self.source.rfind("}")
            if close >= 0:
                line_no = self.source[:close].count("\n") + 1
                fixes.append((line_no, "Insert default return 0 in int main", "return 0;"))
        return fixes

    def apply(self, selected=None):
        fixes = self.suggestions()
        selected = set(selected if selected is not None else range(1, len(fixes) + 1))
        lines = self.source.splitlines()
        replacements = {}
        inserts = []
        for index, (line_no, description, replacement) in enumerate(fixes, 1):
            if index not in selected:
                continue
            if description.startswith("Insert missing standard header"):
                inserts.append((max(0, min(line_no - 1, len(lines))), replacement.splitlines()))
            elif description.startswith("Insert default return"):
                close = next((i for i in range(len(lines)-1, -1, -1) if lines[i].strip() == "}"), None)
                if close is not None:
                    lines.insert(close, "    " + replacement)
            elif 1 <= line_no <= len(lines):
                replacements[line_no] = replacement
        for line_no, replacement in replacements.items():
            lines[line_no-1] = replacement
        for pos, block in sorted(inserts, reverse=True):
            lines[pos:pos] = block
        return "\n".join(lines) + ("\n" if self.source.endswith("\n") else "")
