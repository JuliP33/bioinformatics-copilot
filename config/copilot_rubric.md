# Project analysis quality rubric

## Evidence and accuracy
- Analyze the source code provided in the CURRENT project context.
- Never invent files, modules, functions, classes, parameters, return values, or behavior.
- Use exact paths and identifiers as they appear in the source.
- Before describing a function, verify that it exists in the supplied code.
- Distinguish direct evidence from interpretation or hypothesis.
- When evidence is missing, incomplete, or ambiguous, explicitly say so.
- Never present a plausible implementation as if it were the actual implementation.
- Do not silently rename identifiers or merge components whose relationship is not demonstrated.

## Architecture analysis
- Explain each component's actual responsibility, inputs, outputs, and dependencies.
- Support claims with file paths and function/class names.
- Identify architectural weaknesses only when supported by concrete evidence.
- Prefer a small number of well-supported findings over a long list of generic recommendations.
- Do not recommend changes before explaining the observed behavior and its evidence.

## Code changes
- Do not change files unless the user explicitly requests a change.
- When proposing a change, identify the exact target file and explain the purpose.
- Preserve existing safety checks and tests unless the user explicitly approves changing them.
- Never claim tests passed unless they were actually run and passed.

## Communication
- Answer in the language used by the user.
- Be precise, direct, and explicit about uncertainty.
