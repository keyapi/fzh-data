from parse import keep_approval, keep_attachment


def test_keep_completed_agree():
    assert keep_approval("COMPLETED", "agree") is True
    assert keep_approval("完成", "同意") is True


def test_keep_running():
    assert keep_approval("RUNNING", "") is True
    assert keep_approval("审批中", "") is True


def test_drop_cancelled_and_refused():
    assert keep_approval("TERMINATED", "agree") is False
    assert keep_approval("CANCELED", "") is False
    assert keep_approval("已撤销", "") is False
    assert keep_approval("COMPLETED", "refuse") is False
    assert keep_approval("完成", "拒绝") is False


def test_skip_photos_keep_detail_files():
    assert keep_attachment({"kind": "图片", "fileName": "a.png"}) is False
    assert keep_attachment({"kind": "账期明细", "fileName": "AMZ.txt"}) is True
    assert keep_attachment({"kind": "账期明细", "fileName": "inv.pdf"}) is True
    assert keep_attachment({"kind": "账期明细", "fileName": "shot.jpg"}) is False
