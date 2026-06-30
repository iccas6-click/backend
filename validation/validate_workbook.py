from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import openpyxl  # noqa: F401 - required runtime dependency for pandas xlsx reads
import pandas as pd


DEFAULT_WORKBOOK = Path(
    "data/source/drug_supplement_interactions_standardized_v0.21_release_candidate.xlsx"
)

PRIMARY_KEYS = {
    "canonical_drug_entities": "canonical_drug_id",
    "standardized_interactions": "claim_id",
    "raw_interactions": "raw_id",
    "supplement_map": "supplement_id",
    "drug_entity_map": "drug_alias_id",
    "claim_drug_expansion": "expansion_id",
    "claim_target_map": "claim_target_id",
    "review_queue": "record_id",
    "change_log": "change_id",
}

FOREIGN_KEYS = [
    ("standardized_interactions", "raw_id", "raw_interactions", "raw_id"),
    ("standardized_interactions", "supplement_id", "supplement_map", "supplement_id"),
    ("standardized_interactions", "drug_alias_id", "drug_entity_map", "drug_alias_id"),
    (
        "standardized_interactions",
        "canonical_drug_id",
        "canonical_drug_entities",
        "canonical_drug_id",
    ),
    ("claim_target_map", "claim_id", "standardized_interactions", "claim_id"),
    ("claim_drug_expansion", "claim_id", "standardized_interactions", "claim_id"),
    ("claim_target_map", "source_alias_id", "drug_entity_map", "drug_alias_id"),
    (
        "claim_target_map",
        "source_composite_canonical_drug_id",
        "canonical_drug_entities",
        "canonical_drug_id",
    ),
    (
        "claim_target_map",
        "target_canonical_drug_id",
        "canonical_drug_entities",
        "canonical_drug_id",
    ),
    (
        "claim_drug_expansion",
        "source_class_canonical_drug_id",
        "canonical_drug_entities",
        "canonical_drug_id",
    ),
    (
        "claim_drug_expansion",
        "expanded_canonical_drug_id",
        "canonical_drug_entities",
        "canonical_drug_id",
    ),
]

STATUS_COLUMNS = {
    "canonical_drug_entities": ["entity_level", "external_id_status", "mapping_status"],
    "supplement_map": ["entity_type", "mapping_status"],
    "drug_entity_map": ["entity_level", "mapping_status"],
    "standardized_interactions": [
        "source_review_status",
        "supplement_mapping_status",
        "drug_mapping_status",
        "external_id_status",
        "overall_review_status",
    ],
    "claim_target_map": ["relation_type", "review_status"],
    "claim_drug_expansion": ["relation_type", "review_status"],
    "review_queue": ["queue_type", "current_status"],
    "raw_interactions": ["review_status"],
}

INVALID_SHEET_NAME_CHARACTERS = set(r":\/?*[]")
MAX_SHEET_NAME_LENGTH = 31


@dataclass
class Finding:
    level: str
    message: str


def normalize_value(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def excel_row(index: int) -> int:
    return index + 2


def load_workbook_frames(path: Path) -> dict[str, pd.DataFrame]:
    return pd.read_excel(path, sheet_name=None, dtype=object, engine="openpyxl")


def missing_sheet_or_column(
    frames: dict[str, pd.DataFrame], sheet: str, column: str
) -> Finding | None:
    if sheet not in frames:
        return Finding("ERROR", f"{sheet}.{column}: sheet not found")
    if column not in frames[sheet].columns:
        return Finding("ERROR", f"{sheet}.{column}: column not found")
    return None


def check_primary_keys(frames: dict[str, pd.DataFrame]) -> list[Finding]:
    findings: list[Finding] = []
    for sheet, column in PRIMARY_KEYS.items():
        missing = missing_sheet_or_column(frames, sheet, column)
        if missing:
            findings.append(missing)
            continue

        values = frames[sheet][column].map(normalize_value)
        blank_rows = [excel_row(i) for i, value in values.items() if value == ""]
        if blank_rows:
            findings.append(
                Finding(
                    "ERROR",
                    f"{sheet}.{column}: blank primary key at rows {blank_rows}",
                )
            )

        duplicates = values[values != ""]
        duplicate_values = duplicates[duplicates.duplicated(keep=False)]
        for value in sorted(duplicate_values.unique()):
            rows = [excel_row(i) for i, v in values.items() if v == value]
            findings.append(
                Finding(
                    "ERROR",
                    f"{sheet}.{column}: duplicate value {value!r} at rows {rows}",
                )
            )

        if not blank_rows and duplicate_values.empty:
            findings.append(
                Finding("PASS", f"{sheet}.{column}: no blanks or duplicates")
            )
    return findings


def check_foreign_keys(frames: dict[str, pd.DataFrame]) -> list[Finding]:
    findings: list[Finding] = []
    for source_sheet, source_col, target_sheet, target_col in FOREIGN_KEYS:
        missing_source = missing_sheet_or_column(frames, source_sheet, source_col)
        missing_target = missing_sheet_or_column(frames, target_sheet, target_col)
        if missing_source:
            findings.append(missing_source)
            continue
        if missing_target:
            findings.append(missing_target)
            continue

        source_values = frames[source_sheet][source_col].map(normalize_value)
        target_values = set(frames[target_sheet][target_col].map(normalize_value))
        target_values.discard("")

        missing_refs: dict[str, list[int]] = {}
        for index, value in source_values.items():
            if value == "":
                continue
            if value not in target_values:
                missing_refs.setdefault(value, []).append(excel_row(index))

        if missing_refs:
            for value, rows in sorted(missing_refs.items()):
                findings.append(
                    Finding(
                        "ERROR",
                        f"{source_sheet}.{source_col} -> "
                        f"{target_sheet}.{target_col}: value {value!r} not found "
                        f"at source rows {rows}",
                    )
                )
        else:
            findings.append(
                Finding(
                    "PASS",
                    f"{source_sheet}.{source_col} -> {target_sheet}.{target_col}: "
                    "all nonblank values found",
                )
            )
    return findings


def status_distributions(frames: dict[str, pd.DataFrame]) -> list[Finding]:
    findings: list[Finding] = []
    for sheet, columns in STATUS_COLUMNS.items():
        if sheet not in frames:
            findings.append(Finding("WARNING", f"{sheet}: sheet not found"))
            continue
        for column in columns:
            if column not in frames[sheet].columns:
                findings.append(Finding("WARNING", f"{sheet}.{column}: column not found"))
                continue
            values = frames[sheet][column].map(normalize_value).replace("", "(blank)")
            counts = values.value_counts(dropna=False)
            distribution = ", ".join(
                f"{value}={count}" for value, count in counts.items()
            )
            findings.append(Finding("INFO", f"{sheet}.{column}: {distribution}"))
    return findings


def check_worksheet_names(frames: dict[str, pd.DataFrame]) -> list[Finding]:
    findings: list[Finding] = []
    sheet_names = list(frames.keys())

    overlength = [
        f"{name!r} ({len(name)} chars)"
        for name in sheet_names
        if len(name) > MAX_SHEET_NAME_LENGTH
    ]
    if overlength:
        findings.append(
            Finding(
                "ERROR",
                "worksheet names exceed 31 characters: " + ", ".join(overlength),
            )
        )
    else:
        findings.append(Finding("PASS", "worksheet names: all names are 31 chars or fewer"))

    invalid_names = []
    for name in sheet_names:
        invalid_chars = sorted({char for char in name if char in INVALID_SHEET_NAME_CHARACTERS})
        if invalid_chars:
            invalid_names.append(f"{name!r} contains {''.join(invalid_chars)!r}")
    if invalid_names:
        findings.append(
            Finding(
                "ERROR",
                "worksheet names contain invalid Excel characters: "
                + ", ".join(invalid_names),
            )
        )
    else:
        findings.append(
            Finding(
                "PASS",
                r"worksheet names: no invalid characters (: \ / ? * [ ])",
            )
        )

    normalized_names: dict[str, list[str]] = {}
    for name in sheet_names:
        normalized_names.setdefault(name.casefold(), []).append(name)
    duplicates = [names for names in normalized_names.values() if len(names) > 1]
    if duplicates:
        findings.append(
            Finding(
                "ERROR",
                "worksheet names have case-insensitive duplicates: "
                + ", ".join(" / ".join(names) for names in duplicates),
            )
        )
    else:
        findings.append(
            Finding("PASS", "worksheet names: no case-insensitive duplicates")
        )

    return findings


def print_section(title: str, findings: list[Finding]) -> None:
    print(f"\n== {title} ==")
    for finding in findings:
        print(f"[{finding.level}] {finding.message}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only validation for the drug-supplement interaction workbook."
    )
    parser.add_argument(
        "workbook",
        nargs="?",
        type=Path,
        default=DEFAULT_WORKBOOK,
        help=f"Path to the workbook. Default: {DEFAULT_WORKBOOK}",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    workbook_path = args.workbook

    print(f"Workbook: {workbook_path}")
    if not workbook_path.exists():
        print(f"[ERROR] workbook not found: {workbook_path}")
        return 1

    frames = load_workbook_frames(workbook_path)
    print(f"Sheets loaded: {len(frames)}")
    for sheet, frame in frames.items():
        print(f"- {sheet}: rows={len(frame)}, columns={len(frame.columns)}")

    primary_findings = check_primary_keys(frames)
    foreign_findings = check_foreign_keys(frames)
    worksheet_name_findings = check_worksheet_names(frames)
    status_findings = status_distributions(frames)

    print_section("Worksheet Name Checks", worksheet_name_findings)
    print_section("Primary Key Checks", primary_findings)
    print_section("Foreign Key Checks", foreign_findings)
    print_section("Status Distributions", status_findings)

    all_findings = (
        worksheet_name_findings
        + primary_findings
        + foreign_findings
        + status_findings
    )
    error_count = sum(1 for finding in all_findings if finding.level == "ERROR")
    warning_count = sum(1 for finding in all_findings if finding.level == "WARNING")
    pass_count = sum(1 for finding in all_findings if finding.level == "PASS")

    print("\n== Summary ==")
    print(f"PASS: {pass_count}")
    print(f"WARNING: {warning_count}")
    print(f"ERROR: {error_count}")

    return 1 if error_count else 0


if __name__ == "__main__":
    sys.exit(main())
