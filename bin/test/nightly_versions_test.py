import logging
from unittest.mock import patch

import pytest
from lib.compiler_id_lookup import CompilerIdLookup
from lib.nightly_versions import NightlyVersions

EXE_TO_IDS = {
    "/opt/compiler-explorer/gcc-snapshot/bin/g++": {"gsnapshot"},
    "/opt/compiler-explorer/gcc-snapshot/bin/gcc": {"cgsnapshot", "gimplegsnapshot"},
    "/opt/compiler-explorer/gcc-snapshot/bin/gnat": {"gnatsnapshot"},
    "/opt/compiler-explorer/gcc-snapshot/bin/gfortran": {"gfortransnapshot"},
    "/opt/compiler-explorer/gcc-snapshot/bin/as": {"gassnapshot"},
    "/opt/compiler-explorer/clang-trunk/bin/clang++": {"clang_trunk"},
    "/opt/compiler-explorer/clang-trunk/bin/clang": {"cclang_trunk"},
    "/opt/compiler-explorer/clang-trunk/bin/llvm-mc": {"llvmas_trunk"},
    "/opt/compiler-explorer/carbon-trunk/bin/carbon": {"carbon-x86-trunk"},
}


@pytest.fixture(name="nightlies")
def nightlies_fixture():
    lookup = CompilerIdLookup()
    lookup._loaded = True
    lookup._exe_to_ids = EXE_TO_IDS
    with patch("lib.nightly_versions.get_compiler_id_lookup", return_value=lookup):
        yield NightlyVersions(logging.getLogger(__name__))


def test_get_compiler_ids_includes_compilers_using_gcc_siblings(nightlies):
    assert nightlies.get_compiler_ids("/opt/compiler-explorer/gcc-snapshot/bin/g++") == {
        "gsnapshot",
        "cgsnapshot",
        "gimplegsnapshot",
        "gnatsnapshot",
        "gfortransnapshot",
        "gassnapshot",
    }


def test_get_compiler_ids_includes_compilers_using_clang_siblings(nightlies):
    assert nightlies.get_compiler_ids("/opt/compiler-explorer/clang-trunk/bin/clang++") == {
        "clang_trunk",
        "cclang_trunk",
        "llvmas_trunk",
    }


def test_get_compiler_ids_finds_languages_without_sibling_rules(nightlies):
    assert nightlies.get_compiler_ids("/opt/compiler-explorer/carbon-trunk/bin/carbon") == {"carbon-x86-trunk"}


def test_get_compiler_ids_is_empty_for_unknown_exe(nightlies):
    assert nightlies.get_compiler_ids("/opt/compiler-explorer/unknown-trunk/bin/unknown") == set()


def test_update_version_maps_every_compiler_id_to_the_checked_exe(nightlies):
    exe = "/opt/compiler-explorer/clang-trunk/bin/clang++"
    with patch("lib.nightly_versions.dynamodb_client") as dynamodb:
        nightlies.update_version(exe, "1759795200.0", "clang version 22.0.0", "clang version 22.0.0\nTarget: x86_64")

    written = [call.kwargs for call in dynamodb.put_item.call_args_list]
    assert written[0] == {
        "TableName": "nightly-version",
        "Item": {
            "exe": {"S": exe},
            "modified": {"N": "1759795200.0"},
            "version": {"S": "clang version 22.0.0"},
            "full_version": {"S": "clang version 22.0.0\nTarget: x86_64"},
        },
    }
    assert sorted(written[1:], key=lambda item: item["Item"]["id"]["S"]) == [
        {"TableName": "nightly-exe", "Item": {"id": {"S": compiler_id}, "exe": {"S": exe}}}
        for compiler_id in ["cclang_trunk", "clang_trunk", "llvmas_trunk"]
    ]


def test_update_version_skips_exe_without_compiler_ids(nightlies):
    with patch("lib.nightly_versions.dynamodb_client") as dynamodb:
        nightlies.update_version("/opt/compiler-explorer/unknown-trunk/bin/unknown", "0", "v", "v")

    dynamodb.put_item.assert_not_called()
