#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""物理文件管理：分块上传、大小上限、哈希、原子发布、路径越界防护。"""

from __future__ import annotations

import io

import pytest

from web import storage


def test_save_upload_stream_reports_size_and_hash(tmp_path):
    data = b"hello pb orders" * 1000
    dest = tmp_path / "in" / "upload.pdf"
    size, digest = storage.save_upload_stream(io.BytesIO(data), dest, max_bytes=10_000_000)

    assert size == len(data)
    assert dest.read_bytes() == data
    assert digest == storage.sha256_file(dest)


def test_save_upload_stream_rejects_oversize_and_cleans_partial(tmp_path):
    dest = tmp_path / "upload.pdf"
    with pytest.raises(storage.UploadTooLarge):
        storage.save_upload_stream(io.BytesIO(b"x" * 5000), dest, max_bytes=1000)
    assert not dest.exists()


def test_validate_upload_name_checks_the_slot_suffix():
    assert storage.validate_upload_name("Packslip 美中 x50.pdf", "Packslip PDF", ".pdf") == "Packslip 美中 x50.pdf"
    assert storage.validate_upload_name("order x40.csv", "订单 CSV", ".csv") == "order x40.csv"
    with pytest.raises(ValueError):
        storage.validate_upload_name("order.csv", "Packslip PDF", ".pdf")


def test_validate_upload_name_strips_directory_components():
    assert storage.safe_display_name(r"C:\tmp\..\secret\a.pdf") == "a.pdf"
    assert storage.safe_display_name("/etc/shadow") == "shadow"


def test_validate_upload_name_rejects_other_suffixes():
    with pytest.raises(ValueError):
        storage.validate_upload_name("payload.exe", "Packslip PDF", ".pdf")
    with pytest.raises(ValueError):
        storage.validate_upload_name("/etc/passwd", "Packslip PDF", ".pdf")


def test_publish_artifact_is_content_addressed(tmp_path):
    src = tmp_path / "work" / "label.pdf"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"same-bytes")
    arts = tmp_path / "artifacts"

    rel, size, digest = storage.publish_artifact(src, arts, "label.pdf")
    assert size == 10
    assert not src.exists()
    assert (arts / rel).is_file()
    assert digest == storage.sha256_file(arts / rel)

    # 同内容再发布一次：复用同一物理文件，不重复占盘
    src2 = tmp_path / "work" / "label2.pdf"
    src2.write_bytes(b"same-bytes")
    rel2, _, digest2 = storage.publish_artifact(src2, arts, "label.pdf")
    assert rel2 == rel and digest2 == digest
    assert not src2.exists()


def test_resolve_artifact_path_blocks_traversal(tmp_path):
    arts = tmp_path / "artifacts"
    (arts / "ab").mkdir(parents=True)
    good = arts / "ab" / "x.pdf"
    good.write_bytes(b"%PDF")

    assert storage.resolve_artifact_path(arts, "ab/x.pdf") == good.resolve()

    outside = tmp_path / "outsider.pdf"
    outside.write_bytes(b"%PDF")
    with pytest.raises(storage.StoredPathError):
        storage.resolve_artifact_path(arts, "../outsider.pdf")
    with pytest.raises(storage.StoredPathError):
        storage.resolve_artifact_path(arts, "ab/missing.pdf")


def test_clone_inputs_copies_files(tmp_path):
    src, dest = tmp_path / "a", tmp_path / "b"
    src.mkdir()
    (src / "one.pdf").write_bytes(b"1")
    (src / "two.csv").write_bytes(b"2")

    names = storage.clone_inputs(src, dest)
    assert names == ["one.pdf", "two.csv"]
    assert (dest / "one.pdf").read_bytes() == b"1"


def test_publish_input_copy_keeps_source_and_dedupes(tmp_path):
    """输入的登记：内容寻址去重，但**绝不移走原文件**。

    回归：`publish_artifact` 用 os.replace 移走源文件（产物一次性，移走省磁盘）；
    输入不能这么干 —— inputs/ 里那份还要给 worker 用、还要供「用相同输入重新处理」。
    """
    artifacts = tmp_path / "artifacts"
    src_a = tmp_path / "job-a" / "order.csv"
    src_b = tmp_path / "job-b" / "order.csv"
    for src in (src_a, src_b):
        src.parent.mkdir(parents=True)
        src.write_bytes(b"same,content\n")

    rel_a, size_a, hash_a = storage.publish_input_copy(src_a, artifacts)
    rel_b, size_b, hash_b = storage.publish_input_copy(src_b, artifacts)

    assert src_a.is_file() and src_b.is_file(), "原文件被移走了"
    assert rel_a == rel_b and hash_a == hash_b, "同内容应去重成同一份"
    assert size_a == size_b == len(b"same,content\n")
    assert len([p for p in artifacts.rglob("*") if p.is_file()]) == 1


def test_same_display_name_different_content_keeps_both(tmp_path):
    """同名但内容不同：两份都保留，靠内容哈希区分（互不覆盖）。"""
    artifacts = tmp_path / "artifacts"
    a = tmp_path / "job-a" / "order.csv"
    b = tmp_path / "job-b" / "order.csv"
    a.parent.mkdir(parents=True); a.write_bytes(b"v1\n")
    b.parent.mkdir(parents=True); b.write_bytes(b"v2,longer\n")

    rel_a, _, hash_a = storage.publish_input_copy(a, artifacts)
    rel_b, _, hash_b = storage.publish_input_copy(b, artifacts)

    assert rel_a != rel_b and hash_a != hash_b
    assert len([p for p in artifacts.rglob("*") if p.is_file()]) == 2
    assert a.read_bytes() == b"v1\n" and b.read_bytes() == b"v2,longer\n"
