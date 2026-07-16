"""Command-line utility for runtime storage backup, restore and migration."""
from __future__ import annotations
import argparse
import json
from storage_architecture import (
    create_runtime_backup,
    get_runtime_paths,
    migrate_legacy_runtime,
    restore_runtime_backup,
    storage_manifest,
    write_manifest,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="AI Aksje Analyzer runtime storage administration")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    backup = sub.add_parser("backup")
    backup.add_argument("--output")
    restore = sub.add_parser("restore")
    restore.add_argument("backup_file")
    restore.add_argument("--overwrite", action="store_true")
    migrate = sub.add_parser("migrate")
    migrate.add_argument("--apply", action="store_true", help="Copy files. Default is dry-run.")
    args = parser.parse_args()

    if args.command == "status":
        write_manifest()
        print(json.dumps(storage_manifest(), ensure_ascii=False, indent=2))
    elif args.command == "backup":
        print(create_runtime_backup(args.output))
    elif args.command == "restore":
        print(restore_runtime_backup(args.backup_file, overwrite=args.overwrite))
    elif args.command == "migrate":
        print(json.dumps(migrate_legacy_runtime(dry_run=not args.apply), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
