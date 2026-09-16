# Code Complexity

## About

Code Complexity is a Python command-line tool designed to provide an empirical, quantitative measure of how complex a program is.

Code Complexity explores different aspects of a program's structure and syntax and produces an overall numerical score. This score can be used to analyse and compare programs using a consistent set of complexity measurements.

The scoring system is based on the types of syntax nodes identified during analysis. Each supported node type is assigned a weight representing its contribution to the overall complexity score.

The same scoring system can be applied to different programming languages where the corresponding syntax can be represented by the supported node types.

Please choose the branch that represents the language used for your test.

## Code Analysis

The program scans the source code and constructs an Abstract Syntax Tree (AST). The AST is then traversed and the complexity of each relevant node is calculated using its assigned weight.

The basic scoring formula is:

**Complexity Score = `Σ(Node Weight × Nesting Multiplier)`**

Nodes that are not assigned a weight do not contribute to the score.

### Scoring Criteria

The following are the default weights used by Code Complexity:

| Category                      | Type                              | Weight |
| ----------------------------- | --------------------------------- | -----: |
| **Expressions / Operators**   | `BinaryOperator`                  |   1.00 |
|                               | `UnaryOperator`                   |   0.75 |
|                               | `CompoundAssignOperator`          |   1.00 |
|                               | `ConditionalOperator`             |   1.50 |
|                               | `CXXOperatorCallExpr`             |   1.25 |
| **Declarations**              | `VarDecl`                         |   0.50 |
|                               | `FieldDecl`                       |   0.50 |
|                               | `ParmVarDecl`                     |   0.25 |
| **Calls / Object Operations** | `CallExpr`                        |   1.00 |
|                               | `CXXMemberCallExpr`               |   1.00 |
|                               | `CXXConstructExpr`                |   1.00 |
|                               | `CXXNewExpr`                      |   1.50 |
|                               | `CXXDeleteExpr`                   |   1.00 |
| **Control Flow**              | `IfStmt`                          |   2.00 |
|                               | `ForStmt`                         |   2.00 |
|                               | `CXXForRangeStmt`                 |   2.00 |
|                               | `WhileStmt`                       |   2.00 |
|                               | `DoStmt`                          |   2.00 |
|                               | `SwitchStmt`                      |   2.00 |
|                               | `CaseStmt`                        |   1.00 |
|                               | `DefaultStmt`                     |   1.00 |
|                               | `BreakStmt`                       |   0.50 |
|                               | `ContinueStmt`                    |   0.50 |
|                               | `GotoStmt`                        |   1.00 |
|                               | `IndirectGotoStmt`                |   1.00 |
| **Exceptions**                | `CXXTryStmt`                      |   2.00 |
|                               | `CXXCatchStmt`                    |   2.00 |
|                               | `CXXThrowExpr`                    |   2.00 |
| **Functions**                 | `FunctionDecl`                    |   2.00 |
|                               | `CXXMethodDecl`                   |   2.00 |
|                               | `CXXConversionDecl`               |   2.00 |
|                               | `CXXConstructorDecl`              |   2.50 |
|                               | `CXXDestructorDecl`               |   2.50 |
| **Types**                     | `CXXRecordDecl`                   |   2.00 |
|                               | `ClassTemplateDecl`               |   3.00 |
|                               | `ClassTemplateSpecializationDecl` |   2.00 |
|                               | `FunctionTemplateDecl`            |   3.00 |
|                               | `EnumDecl`                        |   1.50 |
|                               | `EnumConstantDecl`                |   0.25 |
|                               | `TypedefDecl`                     |   0.50 |
|                               | `TypeAliasDecl`                   |   0.50 |
| **Other Expressions**         | `LambdaExpr`                      |   2.00 |
|                               | `InitListExpr`                    |   0.50 |
|                               | `CXXBindTemporaryExpr`            |   0.25 |
|                               | `MaterializeTemporaryExpr`        |   0.25 |
|                               | `CXXDefaultArgExpr`               |   0.25 |
| **Statements / Literals**     | `ReturnStmt`                      |   0.75 |
|                               | `CXXNullPtrLiteralExpr`           |   0.10 |
|                               | `DeclStmt`                        |   0.25 |

These are the **default weights**. They can be overridden using the `--weight` command-line option.

For example:

```text
--weight IfStmt=3.0
```

Multiple weights can be specified:

```text
--weight IfStmt=3.0 --weight ForStmt=3.0
```

This allows the scoring model to be adjusted without changing the program itself.

## Nesting

The complexity contribution of nodes within nested control-flow structures is increased using a nesting multiplier.

The multiplier is calculated as:

```text
1.00 + (control depth × 0.05)
```

The multiplier is capped at **1.50**.

| Control-flow depth | Multiplier |
| -----------------: | ---------: |
|                  0 |       1.00 |
|                  1 |       1.05 |
|                  2 |       1.10 |
|                  3 |       1.15 |
|                  4 |       1.20 |
|                  5 |       1.25 |
|                  6 |       1.30 |
|                  7 |       1.35 |
|                  8 |       1.40 |
|                  9 |       1.45 |
|                10+ |       1.50 |

For example, a node with a base weight of `2.00` at a control-flow depth of 3 contributes:

```text
2.00 × 1.15 = 2.30
```

This means that the same type of syntax can contribute more complexity when it occurs inside increasingly nested control flow.

## Recursion

Recursive function calls receive an additional fixed complexity cost of **2.00**.

This cost is added in addition to the normal weight assigned to the call node.

## Implicit Nodes

Implicit AST nodes generated during parsing are excluded from the complexity score.

This prevents implementation details generated by the language frontend from artificially increasing the complexity of the source program.

## Complexity Breakdown

The total score can be divided into several categories:

- **Control flow**
- **Function calls**
- **Declarations**
- **Expressions**
- **Statements**
- **Other**

The category breakdown shows how much each type of syntax contributed to the overall score.

## Additional Metrics

When detailed output is enabled, Code Complexity reports additional measurements alongside the overall score:

- **Score** — the total weighted complexity score.
- **Non-empty LOC** — the number of non-empty lines in the source.
- **AST nodes** — the number of non-implicit AST nodes analysed.
- **Statements** — the number of statement nodes identified.
- **Complexity / LOC** — complexity score divided by non-empty lines of code.
- **Complexity / AST node** — complexity score divided by the number of analysed AST nodes.
- **Max AST depth** — the maximum depth of the AST.
- **Max control nesting** — the maximum depth of nested control-flow structures.
- **Diagnostics** — diagnostics produced by the language frontend.
- **Score breakdown** — the contribution from each complexity category.
- **Functions** — complexity information for individual functions, where supported by the language frontend.

## Interpreting the Score

The complexity score is intended to provide a **relative quantitative measurement** of program complexity.

A higher score indicates that the analysed program contains more syntax that has been assigned a complexity contribution, or that the syntax occurs within more deeply nested control flow.

The score should therefore be interpreted in the context of the programs being compared.

For example, programs can be compared using:

- Total complexity
- Complexity per line of code
- Complexity per AST node
- Maximum control-flow nesting
- Per-function complexity
- Category-level complexity

For meaningful comparisons, programs should ideally be analysed using the same weighting configuration and compatible language/frontend settings.

## Language Support

The scoring model is designed to be independent of a particular programming language. A language frontend is responsible for converting source code into an AST representation that can be analysed by the scoring system.

Different languages may therefore use different AST node names while mapping equivalent language constructs to the same or similar complexity categories.

The current command-line interface provides a common way to analyse source files, configure the analysis, and produce human-readable, JSON, or CSV output.

## Current Frontend

The current implementation uses **Clang's JSON AST output** as its source of AST information.

This frontend currently provides support for analysing C++ source code and uses Clang's selected language standard when constructing the AST.

The scoring system itself is not intended to be limited to C++, but support for other languages hasn't yet been added.

## Command-Line Usage

**For best results, temporarily remove all references to third party code; for example `#include <string>` or `import sys` as they will be analysed too, breaking the result.**

Basic analysis:

```text
python complexity.py example.cpp
```

Show detailed metrics:

```text
python complexity.py example.cpp --details
```

Analyse a directory:

```text
python complexity.py ./src --details
```

Specify a language/frontend standard where supported:

```text
python complexity.py example.cpp --std c++20
```

Override a node weight:

```text
python complexity.py example.cpp --weight IfStmt=3.0
```

Show the highest-scoring functions:

```text
python complexity.py example.cpp --details --top 10
```

Output JSON:

```text
python complexity.py example.cpp --json
```

Output CSV:

```text
python complexity.py example.cpp --csv
```

## Limitations

The complexity score is a measurement defined by this project rather than a universally standardised complexity metric.

The choice of weights affects the resulting score, so scores produced using different weight configurations should not be directly compared.

The accuracy and available syntax types depend on the language frontend used to generate the AST.

As a result, adding support for another programming language may require mapping that language's AST representation to the complexity model.

> Note: Whilst it is perfectly acceptable to use this to compare programs written in the same language, it should not be used to compare programs written in different languages, like for example comparing the complexity of a Python and a C++ file against each other is frowned upon.
