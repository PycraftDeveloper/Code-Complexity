#!/usr/bin/env python3

#type: ignore

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


# ============================================================
# Configuration
# ============================================================

DEFAULT_CLANG = Path(r"C:\Program Files\LLVM\bin\clang++.EXE")
DEFAULT_STANDARD = "c++20"


DEFAULT_WEIGHTS: dict[str, float] = {
    # Expressions / operators
    "BinaryOperator": 1.0,
    "UnaryOperator": 0.75,
    "CompoundAssignOperator": 1.0,
    "ConditionalOperator": 1.5,
    "CXXOperatorCallExpr": 1.25,

    # Declarations
    "VarDecl": 0.5,
    "FieldDecl": 0.5,
    "ParmVarDecl": 0.25,

    # Calls / object operations
    "CallExpr": 1.0,
    "CXXMemberCallExpr": 1.0,
    "CXXConstructExpr": 1.0,
    "CXXNewExpr": 1.5,
    "CXXDeleteExpr": 1.0,

    # Control flow
    "IfStmt": 2.0,
    "ForStmt": 2.0,
    "CXXForRangeStmt": 2.0,
    "WhileStmt": 2.0,
    "DoStmt": 2.0,
    "SwitchStmt": 2.0,
    "CaseStmt": 1.0,
    "DefaultStmt": 1.0,
    "BreakStmt": 0.5,
    "ContinueStmt": 0.5,
    "GotoStmt": 1.0,
    "IndirectGotoStmt": 1.0,

    # Exceptions
    "CXXTryStmt": 2.0,
    "CXXCatchStmt": 2.0,
    "CXXThrowExpr": 2.0,

    # Functions
    "FunctionDecl": 2.0,
    "CXXMethodDecl": 2.0,
    "CXXConversionDecl": 2.0,
    "CXXConstructorDecl": 2.5,
    "CXXDestructorDecl": 2.5,

    # Types
    "CXXRecordDecl": 2.0,
    "ClassTemplateDecl": 3.0,
    "ClassTemplateSpecializationDecl": 2.0,
    "FunctionTemplateDecl": 3.0,
    "EnumDecl": 1.5,
    "EnumConstantDecl": 0.25,
    "TypedefDecl": 0.5,
    "TypeAliasDecl": 0.5,

    # Other expressions
    "LambdaExpr": 2.0,
    "InitListExpr": 0.5,
    "CXXBindTemporaryExpr": 0.25,
    "MaterializeTemporaryExpr": 0.25,
    "CXXDefaultArgExpr": 0.25,

    # Statements / literals
    "ReturnStmt": 0.75,
    "CXXNullPtrLiteralExpr": 0.1,
    "DeclStmt": 0.25,
}


CONTROL_NODES = {
    "IfStmt",
    "ForStmt",
    "CXXForRangeStmt",
    "WhileStmt",
    "DoStmt",
    "SwitchStmt",
    "CXXTryStmt",
    "CXXCatchStmt",
}


FUNCTION_NODES = {
    "FunctionDecl",
    "CXXMethodDecl",
    "CXXConversionDecl",
    "CXXConstructorDecl",
    "CXXDestructorDecl",
}


# Used only to make the --details score breakdown readable.
CATEGORY_NODES: dict[str, set[str]] = {
    "Control flow": {
        "IfStmt",
        "ForStmt",
        "CXXForRangeStmt",
        "WhileStmt",
        "DoStmt",
        "SwitchStmt",
        "CaseStmt",
        "DefaultStmt",
        "BreakStmt",
        "ContinueStmt",
        "GotoStmt",
        "IndirectGotoStmt",
        "CXXTryStmt",
        "CXXCatchStmt",
        "CXXThrowExpr",
    },
    "Function calls": {
        "CallExpr",
        "CXXMemberCallExpr",
        "CXXOperatorCallExpr",
        "CXXConstructExpr",
        "CXXNewExpr",
        "CXXDeleteExpr",
    },
    "Declarations": {
        "VarDecl",
        "FieldDecl",
        "ParmVarDecl",
        "FunctionDecl",
        "CXXMethodDecl",
        "CXXConversionDecl",
        "CXXConstructorDecl",
        "CXXDestructorDecl",
        "CXXRecordDecl",
        "ClassTemplateDecl",
        "ClassTemplateSpecializationDecl",
        "FunctionTemplateDecl",
        "EnumDecl",
        "EnumConstantDecl",
        "TypedefDecl",
        "TypeAliasDecl",
    },
    "Expressions": {
        "BinaryOperator",
        "UnaryOperator",
        "CompoundAssignOperator",
        "ConditionalOperator",
        "LambdaExpr",
        "InitListExpr",
        "CXXBindTemporaryExpr",
        "MaterializeTemporaryExpr",
        "CXXDefaultArgExpr",
        "CXXNullPtrLiteralExpr",
    },
    "Statements": {
        "ReturnStmt",
        "DeclStmt",
    },
}


# ============================================================
# Data classes
# ============================================================

@dataclass
class ASTNode:
    kind: str
    name: str | None
    line: int | None
    end_line: int | None
    depth: int
    source_file: str
    implicit: bool
    obj: dict[str, Any]


@dataclass
class FunctionInfo:
    name: str
    kind: str
    score: float
    calls: int
    recursive_calls: int
    max_control_nesting: int


@dataclass
class AnalysisResult:
    path: str
    score: float
    loc: int
    ast_nodes: int
    statements: int
    complexity_per_loc: float
    complexity_per_ast_node: float
    max_ast_depth: int
    max_control_nesting: int
    diagnostics: int
    diagnostic_text: str
    breakdown: dict[str, float]
    functions: list[FunctionInfo]


# ============================================================
# Path handling
# ============================================================

def canonical_path(path: str | Path) -> Path:
    """
    Resolve a path as far as possible without requiring it to exist.
    """
    path = Path(path)

    try:
        return path.resolve(strict=False)
    except OSError:
        return Path(os.path.abspath(os.path.normpath(str(path))))


def same_file(a: str | Path, b: str | Path) -> bool:
    """
    Compare paths in a Windows-friendly way.
    """
    return (
        os.path.normcase(str(canonical_path(a)))
        == os.path.normcase(str(canonical_path(b)))
    )


# ============================================================
# Clang
# ============================================================

def find_clang() -> Path:
    """
    Find clang++.exe.

    The default is the normal LLVM Windows installation path.
    """
    candidates = [
        DEFAULT_CLANG,
        Path("clang++.exe"),
        Path("clang++"),
    ]

    for candidate in candidates:
        if candidate.is_file():
            return candidate

    # Let PATH resolve clang++ if it exists there.
    for name in ("clang++.exe", "clang++"):
        try:
            result = subprocess.run(
                [name, "--version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                return Path(name)

        except (FileNotFoundError, OSError):
            pass

    raise FileNotFoundError(
        "Could not find clang++.exe.\n"
        f"Expected: {DEFAULT_CLANG}\n"
        "Use --clang to specify the executable."
    )


def run_clang_ast(
    source: Path,
    clang: Path,
    standard: str = DEFAULT_STANDARD,
) -> tuple[str, str]:
    """
    Run Clang's JSON AST dump.

    The source is intentionally compiled without include paths or project
    configuration. The test files are expected to have their includes removed.

    Clang is allowed to fail syntactically. We only require it to produce
    an AST on stdout.
    """
    command = [
        str(clang),
        f"-std={standard}",
        "-fsyntax-only",
        "-Xclang",
        "-ast-dump=json",
        str(source),
    ]

    try:
        process = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        raise RuntimeError(
            f"Failed to execute Clang:\n{exc}"
        ) from exc

    ast = process.stdout.strip()
    diagnostics = process.stderr.strip()

    # Important:
    # A non-zero return code is NOT automatically an error here.
    #
    # These test files are deliberately allowed to contain invalid C++.
    # If Clang recovered enough of the program to emit a JSON AST, we can
    # still analyse it.
    if not ast:
        command_text = " ".join(f'"{x}"' for x in command)

        raise RuntimeError(
            "Clang did not produce an AST.\n\n"
            f"Command:\n{command_text}\n\n"
            f"Diagnostics:\n{diagnostics}"
        )

    return ast, diagnostics


# ============================================================
# AST location helpers
# ============================================================

def get_location_file(location: Any) -> str | None:
    if not isinstance(location, dict):
        return None

    # Macro expansion location.
    expansion = location.get("expansionLoc")

    if isinstance(expansion, dict):
        file_name = expansion.get("file")

        if isinstance(file_name, str):
            return file_name

        nested = get_location_file(expansion)

        if nested:
            return nested

    file_name = location.get("file")

    if isinstance(file_name, str):
        return file_name

    # Spelling location.
    spelling = location.get("spellingLoc")

    if isinstance(spelling, dict):
        file_name = spelling.get("file")

        if isinstance(file_name, str):
            return file_name

        nested = get_location_file(spelling)

        if nested:
            return nested

    return None


def get_location_line(location: Any) -> int | None:
    if not isinstance(location, dict):
        return None

    expansion = location.get("expansionLoc")

    if isinstance(expansion, dict):
        line = get_location_line(expansion)

        if line is not None:
            return line

    line = location.get("line")

    if isinstance(line, int):
        return line

    spelling = location.get("spellingLoc")

    if isinstance(spelling, dict):
        line = get_location_line(spelling)

        if line is not None:
            return line

    return None


def get_node_location(
    obj: dict[str, Any],
) -> tuple[str | None, int | None, int | None]:
    """
    Return:
        source file,
        starting line,
        ending line
    """
    location = obj.get("loc")

    start_file = get_location_file(location)
    start_line = get_location_line(location)

    end_line: int | None = None

    source_range = obj.get("range")

    if isinstance(source_range, dict):
        begin = source_range.get("begin")
        end = source_range.get("end")

        begin_file = get_location_file(begin)
        begin_line = get_location_line(begin)
        end_line = get_location_line(end)

        if start_file is None:
            start_file = begin_file

        if start_line is None:
            start_line = begin_line

    return start_file, start_line, end_line


# ============================================================
# AST traversal
# ============================================================

def node_children(obj: dict[str, Any]) -> list[dict[str, Any]]:
    children = obj.get("inner")

    if not isinstance(children, list):
        return []

    return [
        child
        for child in children
        if isinstance(child, dict)
    ]


def parse_ast_json(
    dump: str,
    target: Path,
) -> tuple[dict[str, Any], list[ASTNode]]:
    """
    Parse Clang's JSON AST and keep only nodes belonging to the target file.

    Clang frequently omits the `file` field for nodes in the main source file.
    Therefore source ownership is inherited from the parent.

    TranslationUnitDecl is always accepted as the root.
    """
    try:
        root = json.loads(dump)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Clang produced invalid JSON AST:\n{exc}"
        ) from exc

    target = canonical_path(target)

    nodes: list[ASTNode] = []

    def walk(
        obj: Any,
        depth: int,
        inherited_file: str | None,
    ) -> None:
        if not isinstance(obj, dict):
            return

        kind = obj.get("kind")

        if not isinstance(kind, str):
            kind = ""

        explicit_file, line, end_line = get_node_location(obj)

        current_file = explicit_file or inherited_file

        is_translation_unit = kind == "TranslationUnitDecl"

        if is_translation_unit:
            belongs_to_target = True
        else:
            belongs_to_target = (
                current_file is not None
                and same_file(current_file, target)
            )

        if belongs_to_target and not is_translation_unit:
            name = obj.get("name")

            if not isinstance(name, str):
                name = None

            nodes.append(
                ASTNode(
                    kind=kind,
                    name=name,
                    line=line,
                    end_line=end_line,
                    depth=depth,
                    source_file=(
                        str(canonical_path(current_file))
                        if current_file
                        else str(target)
                    ),
                    implicit=bool(obj.get("isImplicit", False)),
                    obj=obj,
                )
            )

        for child in node_children(obj):
            child_file, _, _ = get_node_location(child)

            next_file = child_file or current_file

            walk(
                child,
                depth + 1,
                next_file,
            )

    walk(
        root,
        0,
        str(target),
    )

    return root, nodes


# ============================================================
# Source statistics
# ============================================================

def count_loc(path: Path) -> int:
    """
    Count non-empty source lines.

    This deliberately remains simple because the metric is only a
    normalization value; the actual complexity score comes from the AST.
    """
    try:
        with path.open(
            "r",
            encoding="utf-8",
            errors="replace",
        ) as file:
            return sum(
                1
                for line in file
                if line.strip()
            )

    except OSError:
        return 0


def count_statements(root: dict[str, Any]) -> int:
    """
    Count statement nodes in the target AST.

    This is intentionally separate from the weighted score.
    """
    count = 0

    def walk(obj: Any) -> None:
        nonlocal count

        if not isinstance(obj, dict):
            return

        kind = obj.get("kind")

        if isinstance(kind, str) and kind.endswith("Stmt"):
            count += 1

        for child in node_children(obj):
            walk(child)

    walk(root)

    return count


# ============================================================
# Scoring helpers
# ============================================================

def category_for_node(kind: str) -> str:
    for category, node_kinds in CATEGORY_NODES.items():
        if kind in node_kinds:
            return category

    return "Other"


def nesting_multiplier(control_depth: int) -> float:
    """
    Add up to 50% for nested control flow.

    Depth 0 -> 1.00
    Depth 1 -> 1.05
    Depth 2 -> 1.10
    ...
    Depth 10+ -> 1.50
    """
    return 1.0 + min(
        control_depth * 0.05,
        0.50,
    )


def extract_callee_name(obj: dict[str, Any]) -> str | None:
    """
    Best-effort extraction of a called function/method name.
    """
    direct = obj.get("name")

    if isinstance(direct, str):
        return direct

    for child in node_children(obj):
        kind = child.get("kind")

        if kind in {
            "DeclRefExpr",
            "MemberExpr",
            "CXXDependentScopeMemberExpr",
        }:
            name = child.get("name")

            if isinstance(name, str):
                return name

            referenced = child.get("referencedDecl")

            if isinstance(referenced, dict):
                name = referenced.get("name")

                if isinstance(name, str):
                    return name

    return None


# ============================================================
# Function analysis
# ============================================================

def calculate_function_info(
    function_obj: dict[str, Any],
    target: Path,
    weights: dict[str, float],
) -> FunctionInfo:
    """
    Calculate the score attributable to one function body.

    The function declaration itself is not counted here because it is
    already included in the global score.
    """
    function_name = function_obj.get("name")

    if not isinstance(function_name, str):
        function_name = "<anonymous>"

    function_kind = function_obj.get("kind")

    if not isinstance(function_kind, str):
        function_kind = "Function"

    score = 0.0
    calls = 0
    recursive_calls = 0
    max_control_nesting = 0

    def walk(
        obj: Any,
        control_depth: int,
        inherited_file: str | None,
        is_root: bool = False,
    ) -> None:
        nonlocal score
        nonlocal calls
        nonlocal recursive_calls
        nonlocal max_control_nesting

        if not isinstance(obj, dict):
            return

        kind = obj.get("kind")

        if not isinstance(kind, str):
            kind = ""

        explicit_file, _, _ = get_node_location(obj)

        current_file = explicit_file or inherited_file

        # Don't score nodes outside the target source file.
        if not is_root:
            if (
                current_file is None
                or not same_file(current_file, target)
            ):
                return

        # Do not count implicit AST machinery.
        implicit = bool(obj.get("isImplicit", False))

        if implicit:
            return

        # Don't recursively enter another function declaration.
        if not is_root and kind in FUNCTION_NODES:
            return

        node_control_depth = control_depth

        if kind in CONTROL_NODES:
            node_control_depth += 1

            max_control_nesting = max(
                max_control_nesting,
                node_control_depth,
            )

        weight = weights.get(kind, 0.0)

        if weight:
            score += weight * nesting_multiplier(
                node_control_depth
            )

        if kind in {
            "CallExpr",
            "CXXMemberCallExpr",
            "CXXOperatorCallExpr",
        }:
            calls += 1

            callee = extract_callee_name(obj)

            if callee == function_name:
                recursive_calls += 1

                # Recursion gets a small explicit additional cost.
                score += 2.0

        for child in node_children(obj):
            child_file, _, _ = get_node_location(child)

            walk(
                child,
                node_control_depth,
                child_file or current_file,
                False,
            )

    walk(
        function_obj,
        0,
        str(target),
        True,
    )

    return FunctionInfo(
        name=function_name,
        kind=function_kind,
        score=score,
        calls=calls,
        recursive_calls=recursive_calls,
        max_control_nesting=max_control_nesting,
    )


# ============================================================
# Main score calculation
# ============================================================

def calculate_score(
    root: dict[str, Any],
    target: Path,
    weights: dict[str, float],
) -> tuple[
    float,
    int,
    int,
    dict[str, float],
    int,
    list[FunctionInfo],
]:
    """
    Calculate the complete AST complexity score.

    Returns:
        score
        AST node count
        maximum AST depth
        score breakdown
        maximum control nesting
        function information
    """
    score = 0.0
    ast_node_count = 0
    max_ast_depth = 0
    max_control_nesting = 0

    breakdown: dict[str, float] = defaultdict(float)
    functions: list[FunctionInfo] = []

    target = canonical_path(target)

    def walk(
        obj: Any,
        depth: int,
        control_depth: int,
        inherited_file: str | None,
    ) -> None:
        nonlocal score
        nonlocal ast_node_count
        nonlocal max_ast_depth
        nonlocal max_control_nesting

        if not isinstance(obj, dict):
            return

        kind = obj.get("kind")

        if not isinstance(kind, str):
            kind = ""

        explicit_file, _, _ = get_node_location(obj)

        current_file = explicit_file or inherited_file

        is_translation_unit = kind == "TranslationUnitDecl"

        if not is_translation_unit:
            if (
                current_file is None
                or not same_file(current_file, target)
            ):
                return

        if is_translation_unit:
            node_control_depth = control_depth

        else:
            node_control_depth = control_depth

            if kind in CONTROL_NODES:
                node_control_depth += 1

                max_control_nesting = max(
                    max_control_nesting,
                    node_control_depth,
                )

        if not is_translation_unit:
            max_ast_depth = max(
                max_ast_depth,
                depth,
            )

        # ----------------------------------------------------
        # Implicit nodes
        # ----------------------------------------------------
        implicit = bool(obj.get("isImplicit", False))

        if not is_translation_unit and not implicit:
            ast_node_count += 1

            weight = weights.get(kind, 0.0)

            if weight:
                contribution = (
                    weight
                    * nesting_multiplier(node_control_depth)
                )

                score += contribution

                breakdown[
                    category_for_node(kind)
                ] += contribution

        # ----------------------------------------------------
        # Functions
        # ----------------------------------------------------
        if (
            not is_translation_unit
            and not implicit
            and kind in FUNCTION_NODES
        ):
            functions.append(
                calculate_function_info(
                    obj,
                    target,
                    weights,
                )
            )

            # Function bodies are still traversed for the global score.
            # Nested function declarations are ignored by the function
            # analysis above, but they remain valid AST nodes globally.

        # ----------------------------------------------------
        # Children
        # ----------------------------------------------------
        for child in node_children(obj):
            child_file, _, _ = get_node_location(child)

            walk(
                child,
                depth + 1,
                node_control_depth,
                child_file or current_file,
            )

    walk(
        root,
        0,
        0,
        str(target),
    )

    return (
        score,
        ast_node_count,
        max_ast_depth,
        dict(breakdown),
        max_control_nesting,
        functions,
    )


# ============================================================
# Full file analysis
# ============================================================

def analyse_file(
    path: Path,
    clang: Path,
    standard: str,
    weights: dict[str, float],
) -> AnalysisResult:
    ast_dump, diagnostics = run_clang_ast(
        path,
        clang,
        standard,
    )

    root, _ = parse_ast_json(
        ast_dump,
        path,
    )

    (
        score,
        ast_node_count,
        max_ast_depth,
        breakdown,
        max_control_nesting,
        functions,
    ) = calculate_score(
        root,
        path,
        weights,
    )

    loc = count_loc(path)
    statements = count_statements(root)

    complexity_per_loc = (
        score / loc
        if loc
        else 0.0
    )

    complexity_per_ast_node = (
        score / ast_node_count
        if ast_node_count
        else 0.0
    )

    diagnostic_lines = (
        diagnostics.splitlines()
        if diagnostics
        else []
    )

    return AnalysisResult(
        path=str(path),
        score=score,
        loc=loc,
        ast_nodes=ast_node_count,
        statements=statements,
        complexity_per_loc=complexity_per_loc,
        complexity_per_ast_node=complexity_per_ast_node,
        max_ast_depth=max_ast_depth,
        max_control_nesting=max_control_nesting,
        diagnostics=len(diagnostic_lines),
        diagnostic_text=diagnostics,
        breakdown=breakdown,
        functions=functions,
    )


# ============================================================
# File discovery
# ============================================================

SOURCE_EXTENSIONS = {
    ".cpp",
    ".cc",
    ".cxx",
    ".c++",
    ".C",
}


def discover_files(inputs: list[str]) -> list[Path]:
    files: list[Path] = []

    for item in inputs:
        path = Path(item)

        if path.is_file():
            files.append(path)
            continue

        if path.is_dir():
            for candidate in path.rglob("*"):
                if (
                    candidate.is_file()
                    and candidate.suffix in SOURCE_EXTENSIONS
                ):
                    files.append(candidate)

            continue

        print(
            f"Warning: not found: {path}",
            file=sys.stderr,
        )

    # Remove duplicates while preserving order.
    result: list[Path] = []
    seen: set[str] = set()

    for path in files:
        key = os.path.normcase(
            str(canonical_path(path))
        )

        if key not in seen:
            seen.add(key)
            result.append(path)

    return result


# ============================================================
# CLI
# ============================================================

def parse_weight_override(
    value: str,
) -> tuple[str, float]:
    if "=" not in value:
        raise argparse.ArgumentTypeError(
            "Weight must use KIND=VALUE format."
        )

    kind, raw_weight = value.split(
        "=",
        1,
    )

    kind = kind.strip()

    if not kind:
        raise argparse.ArgumentTypeError(
            "Node kind cannot be empty."
        )

    try:
        weight = float(raw_weight)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Invalid weight: {raw_weight}"
        ) from exc

    if weight < 0:
        raise argparse.ArgumentTypeError(
            "Weight cannot be negative."
        )

    return kind, weight


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "C++ technical complexity analyser using "
            "Clang's JSON AST."
        )
    )

    parser.add_argument(
        "paths",
        nargs="+",
        help="C++ source files or directories.",
    )

    parser.add_argument(
        "--clang",
        type=Path,
        default=DEFAULT_CLANG,
        help=(
            "Path to clang++.exe "
            f"(default: {DEFAULT_CLANG})"
        ),
    )

    parser.add_argument(
        "--std",
        default=DEFAULT_STANDARD,
        help=(
            "C++ language standard "
            f"(default: {DEFAULT_STANDARD})"
        ),
    )

    parser.add_argument(
        "--details",
        action="store_true",
        help="Show detailed metrics and score breakdown.",
    )

    parser.add_argument(
        "--top",
        type=int,
        default=0,
        metavar="N",
        help=(
            "Show the N highest-scoring functions "
            "when --details is enabled."
        ),
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="Write results as JSON.",
    )

    parser.add_argument(
        "--csv",
        action="store_true",
        help="Write results as CSV.",
    )

    parser.add_argument(
        "--weight",
        action="append",
        type=parse_weight_override,
        metavar="KIND=VALUE",
        help=(
            "Override an AST node weight. "
            "Can be specified multiple times."
        ),
    )

    return parser


# ============================================================
# Output
# ============================================================

def print_score_only(result: AnalysisResult) -> None:
    """
    Default output.

    Deliberately shows only the score.
    """
    print(
        f"{result.path}: "
        f"{result.score:.2f}"
    )


def print_details(
    result: AnalysisResult,
    top: int = 0,
) -> None:
    print()
    print(result.path)

    print(
        f"  Score:                  "
        f"{result.score:.2f}"
    )

    print(
        f"  Non-empty LOC:          "
        f"{result.loc}"
    )

    print(
        f"  AST nodes:              "
        f"{result.ast_nodes}"
    )

    print(
        f"  Statements:             "
        f"{result.statements}"
    )

    print(
        f"  Complexity / LOC:       "
        f"{result.complexity_per_loc:.3f}"
    )

    print(
        f"  Complexity / AST node:  "
        f"{result.complexity_per_ast_node:.3f}"
    )

    print(
        f"  Max AST depth:          "
        f"{result.max_ast_depth}"
    )

    print(
        f"  Max control nesting:    "
        f"{result.max_control_nesting}"
    )

    print(
        f"  Clang diagnostics:      "
        f"{result.diagnostics}"
    )

    print()
    print("  Score breakdown")

    categories = [
        "Control flow",
        "Function calls",
        "Declarations",
        "Expressions",
        "Statements",
        "Other",
    ]

    for category in categories:
        value = result.breakdown.get(
            category,
            0.0,
        )

        if value:
            percentage = (
                value / result.score * 100
                if result.score
                else 0.0
            )

            print(
                f"    {category:<20}"
                f"{value:>8.2f}"
                f"  ({percentage:>5.1f}%)"
            )

    if result.functions:
        print()
        print("  Functions")

        functions = sorted(
            result.functions,
            key=lambda function: function.score,
            reverse=True,
        )

        if top > 0:
            functions = functions[:top]

        for function in functions:
            recursion = ""

            if function.recursive_calls:
                recursion = (
                    f", recursive calls="
                    f"{function.recursive_calls}"
                )

            print(
                f"    {function.name:<30}"
                f"{function.score:>8.2f}"
                f"  calls={function.calls}"
                f"{recursion}"
                f", nesting={function.max_control_nesting}"
            )

    if result.diagnostic_text:
        print()
        print("  Clang diagnostics")

        for line in result.diagnostic_text.splitlines():
            print(
                f"    {line}"
            )


def print_json(
    results: list[AnalysisResult],
) -> None:
    data = []

    for result in results:
        item = asdict(result)
        data.append(item)

    print(
        json.dumps(
            data,
            indent=2,
        )
    )


def print_csv(
    results: list[AnalysisResult],
) -> None:
    writer = csv.writer(sys.stdout)

    writer.writerow(
        [
            "file",
            "score",
            "loc",
            "ast_nodes",
            "statements",
            "complexity_per_loc",
            "complexity_per_ast_node",
            "max_ast_depth",
            "max_control_nesting",
            "diagnostics",
        ]
    )

    for result in results:
        writer.writerow(
            [
                result.path,
                f"{result.score:.4f}",
                result.loc,
                result.ast_nodes,
                result.statements,
                f"{result.complexity_per_loc:.6f}",
                f"{result.complexity_per_ast_node:.6f}",
                result.max_ast_depth,
                result.max_control_nesting,
                result.diagnostics,
            ]
        )


# ============================================================
# Main
# ============================================================

def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        clang = args.clang

        if not clang.is_file():
            clang = find_clang()

        files = discover_files(args.paths)

        if not files:
            print(
                "No C++ source files found.",
                file=sys.stderr,
            )
            return 1

        weights = dict(DEFAULT_WEIGHTS)

        if args.weight:
            for kind, weight in args.weight:
                weights[kind] = weight

        results: list[AnalysisResult] = []

        for path in files:
            try:
                result = analyse_file(
                    path,
                    clang,
                    args.std,
                    weights,
                )

                results.append(result)

            except Exception as exc:
                print(
                    f"Error analysing {path}: {exc}",
                    file=sys.stderr,
                )

        if not results:
            return 1

        # ----------------------------------------------------
        # JSON / CSV are machine-readable modes.
        # ----------------------------------------------------
        if args.json:
            print_json(results)
            return 0

        if args.csv:
            print_csv(results)
            return 0

        # ----------------------------------------------------
        # Normal human-readable output.
        # ----------------------------------------------------
        if args.details:
            print(
                "C++ TECHNICAL COMPLEXITY — "
                "CLANG JSON AST"
            )
            print(
                f"Files analysed: {len(results)}"
            )
            print(
                f"Clang: {clang}"
            )
            print(
                f"Standard: {args.std}"
            )
            print(
                "Includes: none "
                "(test files are analysed standalone)"
            )

            for result in results:
                print_details(
                    result,
                    args.top,
                )

        else:
            for result in results:
                print_score_only(result)

        return 0

    except KeyboardInterrupt:
        print(
            "\nCancelled.",
            file=sys.stderr,
        )
        return 130

    except Exception as exc:
        print(
            f"Error: {exc}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())