from __future__ import annotations

from lib.amazon import dynamodb_client
from lib.compiler_id_lookup import get_compiler_id_lookup


def _sibling_exes(exe: str) -> set[str]:
    # An install is checked through a single binary (e.g. g++), but the compilers of other languages point at
    # its siblings in the same bin directory. They are the same nightly build, so they share its version.
    if exe.endswith("/g++"):
        bin_dir = exe.removesuffix("g++")
        return {exe, bin_dir + "gcc", bin_dir + "gnat", bin_dir + "gfortran", bin_dir + "as"}
    if exe.endswith("/clang++"):
        bin_dir = exe.removesuffix("clang++")
        return {exe, bin_dir + "clang", bin_dir + "llvm-mc"}
    return {exe}


class NightlyVersions:
    version_table_name: str = "nightly-version"
    exe_table_name: str = "nightly-exe"

    def __init__(self, logger):
        self.logger = logger

    def get_compiler_ids(self, exe: str) -> set[str]:
        lookup = get_compiler_id_lookup()
        return {compiler_id for sibling in _sibling_exes(exe) for compiler_id in lookup.get_compiler_ids(sibling)}

    def update_version(self, exe: str, modified: str, version: str, full_version: str):
        compiler_ids = self.get_compiler_ids(exe)
        if len(compiler_ids) == 0:
            self.logger.warning(f"No compiler ids found for {exe} - not saving compiler version info to AWS")
            return

        dynamodb_client.put_item(
            TableName=self.version_table_name,
            Item={
                "exe": {"S": exe},
                "modified": {"N": modified},
                "version": {"S": version},
                "full_version": {"S": full_version},
            },
        )

        for compiler_id in compiler_ids:
            dynamodb_client.put_item(
                TableName=self.exe_table_name,
                Item={
                    "id": {"S": compiler_id},
                    "exe": {"S": exe},
                },
            )

        return

    def get_version(self, exe: str):
        result = dynamodb_client.get_item(
            TableName=self.version_table_name,
            Key={"exe": {"S": exe}},
            ConsistentRead=True,
        )
        item = result.get("Item")
        if item:
            return {
                "exe": item["exe"]["S"],
                "version": item["version"]["S"],
                "full_version": item["full_version"]["S"],
                "modified": item["modified"]["N"],
            }
        else:
            return None
