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


def test_validate_upload_name_allows_pdf_and_csv():
    assert storage.validate_upload_name("Packslip 美中 x50.pdf", "Packslip PDF") == "Packslip 美中 x50.pdf"
    assert storage.validate_upload_name("order x40.csv", "订单 CSV") == "order x40.csv"


def test_validate_upload_name_strips_directory_components():
    assert storage.safe_display_name(r"C:\tmp\..\secret\a.pdf") == "a.pdf"
    assert storage.safe_display_name("/etc/shadow") == "shadow"


def test_validate_upload_name_rejects_other_suffixes():
    with pytest.raises(ValueError):
        storage.validate_upload_name("payload.exe", "Packslip PDF")
    with pytest.raises(ValueError):
        storage.validate_upload_name("/etc/passwd", "Packslip PDF")


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
