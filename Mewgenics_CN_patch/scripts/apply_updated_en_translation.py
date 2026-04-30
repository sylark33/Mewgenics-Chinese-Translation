import argparse
import csv
from pathlib import Path


def normalize_multiline_text(text: str) -> str:
    return (text or "").replace("\r\n", "\n").replace("\r", "\n")


def load_csv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = reader.fieldnames or []
    return rows, fieldnames


def apply_updates(
    combined_path: Path,
    diff_path: Path,
    updated_csv_path: Path | None = None,
    sync_all_non_zh: bool = False,
    sync_all_keys: bool = False,
) -> tuple[int, int, list[str]]:
    combined_rows, combined_fields = load_csv(combined_path)
    diff_rows, diff_fields = load_csv(diff_path)
    updated_map: dict[str, dict[str, str]] = {}
    updated_fields: list[str] = []

    if updated_csv_path is not None:
        updated_rows, updated_fields = load_csv(updated_csv_path)
        if "KEY" not in updated_fields or "en" not in updated_fields:
            raise ValueError(f"{updated_csv_path} is missing required columns: KEY/en")
        updated_map = {row["KEY"]: row for row in updated_rows}

    for required in ("KEY", "en", "zh"):
        if required not in combined_fields:
            raise ValueError(f"{combined_path} is missing required column: {required}")

    for required in ("KEY", "new_en", "zh", "status"):
        if required not in diff_fields:
            raise ValueError(f"{diff_path} is missing required column: {required}")

    combined_map = {row["KEY"]: row for row in combined_rows}
    diff_map = {row["KEY"]: row for row in diff_rows}
    inserted = 0
    updated = 0
    empty_zh_keys: list[str] = []

    if sync_all_keys:
        if not updated_map:
            raise ValueError("--sync-all-keys requires --updated-csv")

        synced_rows: list[dict[str, str]] = []
        for updated_row in updated_rows:
            key = updated_row["KEY"]
            repo_row = combined_map.get(key, {})
            diff_row = diff_map.get(key, {})

            new_row = {field: "" for field in combined_fields}
            for field in combined_fields:
                if field == "zh":
                    continue
                if field in updated_fields:
                    new_row[field] = updated_row.get(field, "")

            zh = normalize_multiline_text(diff_row.get("zh", repo_row.get("zh", "")))
            if not zh.strip():
                empty_zh_keys.append(key)
            new_row["zh"] = zh

            if key in combined_map:
                updated += 1
            else:
                inserted += 1
            synced_rows.append(new_row)

        with combined_path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=combined_fields)
            writer.writeheader()
            writer.writerows(synced_rows)

        return updated, inserted, empty_zh_keys

    for diff_row in diff_rows:
        key = diff_row["KEY"]
        status = diff_row["status"]
        if updated_map:
            source_row = updated_map.get(key)
            if source_row is None:
                raise ValueError(f"Missing key in updated source CSV: {key}")
            new_en = source_row.get("en", "")
        else:
            new_en = normalize_multiline_text(diff_row.get("new_en", ""))
        zh = normalize_multiline_text(diff_row.get("zh", ""))
        if not zh.strip():
            empty_zh_keys.append(key)

        target = combined_map.get(key)
        if target is None:
            if status != "new_key":
                raise ValueError(f"Missing existing key in combined.csv: {key}")
            new_row = {field: "" for field in combined_fields}
            if updated_map and sync_all_non_zh:
                for field in combined_fields:
                    if field == "zh":
                        continue
                    if field in updated_fields:
                        new_row[field] = updated_map[key].get(field, "")
            else:
                new_row["KEY"] = key
                new_row["en"] = new_en
            new_row["zh"] = zh
            combined_rows.append(new_row)
            combined_map[key] = new_row
            inserted += 1
            continue

        if updated_map and sync_all_non_zh:
            for field in combined_fields:
                if field == "zh":
                    continue
                if field in updated_fields:
                    target[field] = updated_map[key].get(field, "")
        else:
            target["en"] = new_en
        target["zh"] = zh
        updated += 1

    with combined_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=combined_fields)
        writer.writeheader()
        writer.writerows(combined_rows)

    return updated, inserted, empty_zh_keys


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply updated English text and translated Chinese text back into combined.csv."
    )
    parser.add_argument("combined_csv", type=Path, help="Repository combined.csv")
    parser.add_argument("diff_csv", type=Path, help="Edited translation diff CSV")
    parser.add_argument(
        "--updated-csv",
        type=Path,
        default=None,
        help="Optional canonical updated combined.csv to source exact en values from",
    )
    parser.add_argument(
        "--sync-all-non-zh",
        action="store_true",
        help="When used with --updated-csv, sync every non-zh column from the updated CSV",
    )
    parser.add_argument(
        "--sync-all-keys",
        action="store_true",
        help="Sync all keys from the updated CSV while preserving repo zh or diff zh overrides",
    )
    args = parser.parse_args()

    updated, inserted, empty_zh_keys = apply_updates(
        args.combined_csv,
        args.diff_csv,
        args.updated_csv,
        args.sync_all_non_zh,
        args.sync_all_keys,
    )
    print(f"updated_existing={updated}")
    print(f"inserted_new={inserted}")
    print(f"empty_zh={len(empty_zh_keys)}")
    for key in empty_zh_keys:
        print(f"EMPTY_ZH\t{key}")


if __name__ == "__main__":
    main()
