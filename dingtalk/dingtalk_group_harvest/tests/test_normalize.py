from __future__ import annotations

from dingtalk.dingtalk_group_harvest import normalize


def test_safe_filename_strips_windows_illegal_chars():
    name = normalize.safe_filename('a<b>c:d"e/f\\g|h?i*.md')
    assert "/" not in name and "\\" not in name and ":" not in name
    assert name.endswith(".md")


def test_safe_filename_prefixes_time_and_sender():
    name = normalize.safe_filename("报告.md", sender="张三", time="2026-11-03 09:47:59")
    assert name.startswith("20261103_094759_张三_")
    assert name.endswith("报告.md")


def test_extract_doc_links_only_keeps_alidocs_and_ignores_group_notice():
    text = (
        "看这个 https://alidocs.dingtalk.com/i/nodes/abc "
        "还有 https://n.dingtalk.com/dingding/group_notice/index.html?x=1 "
        "和普通链接 https://example.com/a"
    )
    links = normalize.extract_doc_links(text)
    assert links == ["https://alidocs.dingtalk.com/i/nodes/abc"]


def test_message_files_ignores_images_and_keeps_file_refs():
    msg = {
        "messageId": "m1",
        "sender": "张三",
        "createTime": "2026-11-03 09:47:59",
        "resourceRefs": [
            {
                "contentType": "file",
                "name": "分析.md",
                "resourceId": "rid1",
                "resourceIdType": "fileId",
            },
            {
                "resourceId": "@img1",
                "resourceIdType": "mediaId",
                "type": "mediaId",
            },
        ],
    }
    refs = normalize.message_files(msg)
    assert len(refs) == 1
    assert refs[0].name == "分析.md"
    assert refs[0].resource_id == "rid1"


def test_month_parts():
    assert normalize.month_parts("2026-11-03 09:47:59") == ("2026", "11")
