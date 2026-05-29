#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
登录成功后：默认直达添加页（SELLFOX_DIRECT_ADD_PAGE=true）或经列表点「添加多属性商品」；
填写 SPU/款名并选择属性。结束时可阻塞等待；SELLFOX_AUTO_QUIT=false 时不自动关闭浏览器。
"""
from __future__ import annotations

import logging
import os
import sys
import time
import traceback

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from sellfox_config import SELLFOX_CONFIG, validate_sellfox_config
from sellfox_login import SellfoxLogin

os.makedirs("logs", exist_ok=True)
os.makedirs("screenshots", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("logs/sellfox_multi_attr.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


def save_shot(driver, name: str) -> None:
    path = os.path.join("screenshots", name)
    try:
        driver.save_screenshot(path)
        logger.info("截图: %s", path)
    except Exception as e:
        logger.warning("截图失败: %s", e)


# Element UI 2 / Element Plus / 部分定制主题下选项节点类名不一致
_DROPDOWN_OPTION_CSS = (
    "li.el-select-dropdown__item",
    "div.el-select-dropdown__item",
    "li.el-option",
    "div.el-option",
    "li[role='option']",
    "div[role='option']",
    # 赛狐定制（Cursor 浏览器里选项行为 div.sf__select__item）
    "div.sf__select__item",
)


def _first_visible_option_node(driver):
    for css in _DROPDOWN_OPTION_CSS:
        for el in driver.find_elements(By.CSS_SELECTOR, css):
            try:
                if el.is_displayed():
                    return el
            except Exception:
                continue
    return None


def _first_visible_filter_input_in_panel(panel):
    """可搜索 el-select：下拉内常有「搜索」输入框，需输入关键字后选项才会出现或变为可点。"""
    selectors = (
        "input.sf_select__filter__input",
        "input.el-select-dropdown__input",
        "input[placeholder*='搜索']",
        "input[placeholder*='Search']",
    )
    for css in selectors:
        try:
            for inp in panel.find_elements(By.CSS_SELECTOR, css):
                try:
                    if inp.is_displayed():
                        return inp
                except Exception:
                    continue
        except Exception:
            continue
    try:
        for inp in panel.find_elements(
            By.XPATH, ".//input[contains(@placeholder,'搜索')]"
        ):
            try:
                if inp.is_displayed():
                    return inp
            except Exception:
                continue
    except Exception:
        pass
    return None


def _find_visible_dropdown(driver, timeout: float = 18.0):
    """
    先找「可见的选项节点」再反查挂载容器；兼容 el-popper / el-select__popper 及类名差异。
    """
    deadline = time.time() + timeout
    container_selectors = (
        "body > div.el-select-dropdown.el-popper",
        "body > div.el-popper.el-select__popper",
        "body > div.el-select__popper",
        "body > div.el-popper",
        "div.el-select-dropdown",
        "div.el-popper.el-select-dropdown",
    )
    while time.time() < deadline:
        opt = _first_visible_option_node(driver)
        if opt is not None:
            parent = driver.execute_script(
                "return arguments[0].closest("
                "'.el-select-dropdown, .el-select__popper, .el-popper, [class*=\"popper\"]');",
                opt,
            )
            if parent:
                return parent
        # 仅有搜索框、尚未渲染选项时也要视为已打开，否则会长时间等 li
        for sel in container_selectors:
            drops = driver.find_elements(By.CSS_SELECTOR, sel)
            for d in reversed(drops):
                try:
                    if not d.is_displayed():
                        continue
                    if _first_visible_filter_input_in_panel(d):
                        return d
                except Exception:
                    continue
        for sel in container_selectors:
            drops = driver.find_elements(By.CSS_SELECTOR, sel)
            for d in reversed(drops):
                try:
                    if not d.is_displayed():
                        continue
                    for css in _DROPDOWN_OPTION_CSS:
                        if d.find_elements(By.CSS_SELECTOR, css):
                            return d
                except Exception:
                    continue
        time.sleep(0.2)
    raise TimeoutException(
        "未在超时内找到可见的下拉面板（无选项节点且无「搜索」筛选框）"
    )


def _collect_visible_option_elements(root):
    items: list = []
    for css in _DROPDOWN_OPTION_CSS:
        try:
            items.extend(root.find_elements(By.CSS_SELECTOR, css))
        except Exception:
            continue
    return items


def _match_option_element(nodes, option_text: str):
    """
    在可搜索列表中，「子串优先」会误选更长项（如搜「三角靠枕面料」先点到「欧式三角靠枕面料」）。
    顺序：完全相等 → 在包含关键字的候选中取文案最短的一条。
    """
    want = (option_text or "").strip()
    if not want:
        return None
    exact = None
    contains: list[tuple[int, object]] = []
    for li in nodes:
        try:
            if not li.is_displayed():
                continue
            t = (li.text or "").strip() or (
                li.get_attribute("innerText") or ""
            ).strip()
            if t == want:
                exact = li
                break
            if want in t:
                contains.append((len(t), li))
        except Exception:
            continue
    if exact is not None:
        return exact
    if not contains:
        return None
    contains.sort(key=lambda x: x[0])
    return contains[0][1]


def _type_filter_and_pick_option(driver, ddl, option_text: str) -> bool:
    """
    若在面板内找到搜索框：输入关键字再点选项。
    返回 True 表示已成功点击选项；False 表示无搜索框或未找到匹配项（由上层再尝试纯点击列表）。
    """
    fin = _first_visible_filter_input_in_panel(ddl)
    if not fin:
        return False
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'nearest'});", fin)
        time.sleep(0.08)
        driver.execute_script("arguments[0].click();", fin)
        time.sleep(0.1)
        try:
            fin.clear()
        except Exception:
            pass
        try:
            fin.send_keys(Keys.CONTROL + "a")
            fin.send_keys(Keys.BACKSPACE)
        except Exception:
            pass
        fin.send_keys(option_text)
        logger.info("已在属性下拉搜索框输入: %s", option_text)
    except Exception as e:
        logger.warning("属性下拉搜索框输入失败: %s", e)
        return False
    time.sleep(0.55)
    # 面板可能重绘，重新定位
    try:
        ddl2 = _find_visible_dropdown(driver, timeout=8.0)
    except TimeoutException:
        ddl2 = ddl
    deadline = time.time() + 12.0
    target = None
    while time.time() < deadline:
        for root in (ddl2, ddl):
            pool: list = []
            for li in _collect_visible_option_elements(root):
                try:
                    if li.is_displayed():
                        pool.append(li)
                except Exception:
                    continue
            target = _match_option_element(pool, option_text)
            if target:
                break
        if target:
            break
        time.sleep(0.25)
    if not target:
        save_shot(driver, "sellfox_multi_attr_option_not_found_after_filter.png")
        return False
    driver.execute_script("arguments[0].scrollIntoView({block:'nearest'});", target)
    time.sleep(0.08)
    try:
        target.click()
    except Exception:
        driver.execute_script("arguments[0].click();", target)
    time.sleep(0.4)
    return True


def _open_el_select_by_mode(driver, select_el, mode: str) -> None:
    """mode: suffix | input | wrapper | input_space — 每次只执行一种打开方式，避免重复点箭头把下拉关掉。"""
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", select_el)
    time.sleep(0.12)
    tag = (select_el.tag_name or "").lower()
    root = select_el
    if tag == "input":
        try:
            root = select_el.find_element(
                By.XPATH, "./ancestor::div[contains(@class,'el-select')][1]"
            )
        except Exception:
            root = select_el

    if mode == "suffix":
        for css in (
            ".el-select__caret",
            ".el-input__suffix .el-icon-arrow-up",
            ".el-input__suffix .el-icon-arrow-down",
            "i.el-select__caret",
            ".el-input__suffix-inner",
            ".el-input__suffix",
        ):
            try:
                for el in root.find_elements(By.CSS_SELECTOR, css):
                    try:
                        if el.is_displayed():
                            driver.execute_script("arguments[0].click();", el)
                            time.sleep(0.28)
                            return
                    except Exception:
                        continue
            except Exception:
                continue
        return

    if mode == "wrapper":
        try:
            tgt = root if tag == "input" else select_el
            driver.execute_script("arguments[0].click();", tgt)
            time.sleep(0.25)
        except Exception:
            pass
        return

    if mode == "input":
        if tag == "input":
            try:
                select_el.click()
            except Exception:
                driver.execute_script("arguments[0].click();", select_el)
            time.sleep(0.2)
        else:
            try:
                inp = select_el.find_element(
                    By.CSS_SELECTOR, "input.el-input__inner, input[readonly]"
                )
                driver.execute_script("arguments[0].click();", inp)
            except Exception:
                driver.execute_script("arguments[0].click();", select_el)
            time.sleep(0.2)
        return

    if mode == "input_space":
        inp = select_el
        if tag != "input":
            try:
                inp = select_el.find_element(
                    By.CSS_SELECTOR, "input.el-input__inner, input[readonly]"
                )
            except Exception:
                inp = select_el
        driver.execute_script("arguments[0].click();", inp)
        time.sleep(0.12)
        try:
            inp.send_keys(Keys.SPACE)
        except Exception:
            pass
        time.sleep(0.2)


def el_select_pick_option(driver, select_el, option_text: str) -> None:
    """select_el 可以是属性行的 input，也可以是 el-select 容器 div。"""
    opened = False
    modes = ("suffix", "input", "wrapper", "input_space")
    for attempt, mode in enumerate(modes):
        _open_el_select_by_mode(driver, select_el, mode)
        try:
            _find_visible_dropdown(driver, timeout=4.0 if attempt < len(modes) - 1 else 18.0)
            opened = True
            break
        except TimeoutException:
            time.sleep(0.35)
    if not opened:
        save_shot(driver, "sellfox_multi_attr_dropdown_not_open.png")
        raise TimeoutException("多次尝试后仍未展开属性下拉")
    ddl = _find_visible_dropdown(driver, timeout=5.0)
    if _type_filter_and_pick_option(driver, ddl, option_text):
        return

    items: list = _collect_visible_option_elements(ddl)
    if not items:
        items = driver.find_elements(By.CSS_SELECTOR, ",".join(_DROPDOWN_OPTION_CSS))
    seen = set()
    pool: list = []
    for li in items:
        try:
            oid = id(li)
            if oid in seen:
                continue
            seen.add(oid)
            if not li.is_displayed():
                continue
            pool.append(li)
        except Exception:
            continue
    target = _match_option_element(pool, option_text)
    if not target:
        save_shot(driver, "sellfox_multi_attr_option_not_found.png")
        raise RuntimeError(f"下拉中未找到选项: {option_text}")
    driver.execute_script("arguments[0].scrollIntoView({block:'nearest'});", target)
    time.sleep(0.1)
    try:
        target.click()
    except Exception:
        driver.execute_script("arguments[0].click();", target)
    time.sleep(0.4)


def list_attr_selects(driver):
    """
    返回每一行「请选择属性」对应的 **input** 元素（直接点击即可展开下拉）。
    不再依赖 ancestor::div[el-select]，避免结构差异导致静默失败、结果为 0。
    """
    results: list = []

    def _add_inp(el):
        for r in results:
            try:
                if r == el:
                    return
            except Exception:
                pass
        results.append(el)

    candidates = []
    candidates.extend(
        driver.find_elements(By.CSS_SELECTOR, "input[placeholder='请选择属性']")
    )
    candidates.extend(
        driver.find_elements(
            By.XPATH, "//input[contains(@placeholder,'请选择属性')]"
        )
    )
    seen = set()
    for inp in candidates:
        try:
            iid = inp.id
            if iid and iid in seen:
                continue
            if iid:
                seen.add(iid)
            ph = (inp.get_attribute("placeholder") or "").strip()
            if "开发员" in ph:
                continue
            if "属性" not in ph:
                continue
            if not inp.is_displayed():
                continue
            _add_inp(inp)
        except Exception:
            continue

    return results


def ensure_add_page_context(driver) -> None:
    """若添加页在 iframe 内则切入；否则留在 default_content。"""
    driver.switch_to.default_content()
    if driver.find_elements(By.XPATH, "//input[contains(@placeholder,'SPU')]"):
        return
    for fr in driver.find_elements(By.TAG_NAME, "iframe"):
        try:
            driver.switch_to.default_content()
            driver.switch_to.frame(fr)
            if driver.find_elements(By.XPATH, "//input[contains(@placeholder,'SPU')]"):
                logger.info("已切换到包含表单的 iframe")
                return
        except Exception:
            continue
    driver.switch_to.default_content()


def click_add_attribute_row(driver) -> None:
    # 整页用 // 查找
    patterns = (
        "//button[contains(normalize-space(.),'添加属性')]",
        "//button[.//span[contains(.,'添加属性')]]",
        "//span[contains(.,'添加属性')]/ancestor::button[1]",
        "//a[.//span[contains(.,'添加属性')]]",
        "//span[contains(@class,'el-link')][contains(.,'添加属性')]",
    )
    btn = None
    for xp in patterns:
        for el in driver.find_elements(By.XPATH, xp):
            try:
                if el.is_displayed() and el.is_enabled():
                    btn = el
                    break
            except Exception:
                continue
        if btn:
            break
    if not btn:
        save_shot(driver, "sellfox_multi_attr_add_btn_not_found.png")
        raise RuntimeError("未找到「+ 添加属性」按钮")
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
    time.sleep(0.1)
    try:
        btn.click()
    except Exception:
        driver.execute_script("arguments[0].click();", btn)
    time.sleep(0.55)


def ensure_tall_viewport_for_attr_dropdowns(driver, cfg: dict) -> None:
    """
    底部属性行展开时若视口高度不足，弹层可能无法完整渲染，面板内「搜索」输入框不出现。
    将窗口高度至少拉到 1100px（可覆盖用户配置的较小 SELLFOX_WINDOW_SIZE）。
    """
    try:
        w, h = (cfg.get("window_size") or "1280,1200").split(",", 1)
        w_i, h_i = int(w.strip()), int(h.strip())
        h_i = max(h_i, 1100)
        driver.set_window_size(w_i, h_i)
        logger.info("已调整窗口尺寸为 %sx%s（保证属性下拉可展开）", w_i, h_i)
    except Exception as e:
        logger.warning("调整窗口尺寸失败（可忽略）: %s", e)


def fill_basic_info(driver, cfg: dict) -> None:
    wait = WebDriverWait(driver, 20)
    spu_in = None
    for xp in (
        "//input[contains(@placeholder,'SPU')]",
        "//input[contains(@placeholder,'spu')]",
        "//label[contains(.,'SPU')]//following::input[not(@type='hidden')][1]",
    ):
        try:
            spu_in = wait.until(EC.presence_of_element_located((By.XPATH, xp)))
            if spu_in.is_displayed():
                break
        except Exception:
            continue
    if not spu_in:
        raise RuntimeError("未找到 SPU 输入框")
    spu_in.clear()
    spu_in.send_keys(cfg["spu"])

    name_in = None
    for xp in (
        "//input[contains(@placeholder,'款名')]",
        "//label[contains(.,'款名')]//following::input[not(@type='hidden')][1]",
    ):
        try:
            el = driver.find_element(By.XPATH, xp)
            if el.is_displayed():
                name_in = el
                break
        except Exception:
            continue
    if not name_in:
        raise RuntimeError("未找到款名输入框")
    name_in.clear()
    name_in.send_keys(cfg["style_name"])
    logger.info("已填写 SPU=%s 款名=%s", cfg["spu"], cfg["style_name"])


def run_flow() -> bool:
    validate_sellfox_config()
    cfg = SELLFOX_CONFIG
    sf = SellfoxLogin()
    if not sf.login(keep_browser_open=True):
        logger.error("登录失败")
        return False

    driver = sf.driver
    assert driver is not None
    wait = WebDriverWait(driver, 25)

    try:
        if cfg.get("direct_add_page", True):
            logger.info("直达添加页: %s", cfg["add_multi_attr_url"])
            driver.get(cfg["add_multi_attr_url"])
        else:
            driver.get(cfg["multi_attribute_list_url"])
            save_shot(driver, "sellfox_multi_attr_list.png")
            add_btn = None
            for xp in (
                "//button[contains(.,'添加多属性商品')]",
                "//a[contains(.,'添加多属性商品')]",
                "//span[contains(.,'添加多属性商品')]/ancestor::button",
                "//*[contains(@class,'el-button')][contains(.,'添加多属性商品')]",
            ):
                for el in driver.find_elements(By.XPATH, xp):
                    try:
                        if el.is_displayed():
                            add_btn = el
                            break
                    except Exception:
                        continue
                if add_btn:
                    break
            if not add_btn:
                raise RuntimeError("未找到「添加多属性商品」按钮")
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", add_btn)
            time.sleep(0.15)
            add_btn.click()
            time.sleep(1.0)
            cur = driver.current_url or ""
            logger.info("点击「添加多属性商品」后 URL: %s", cur)
            if "addMultiAttr" not in cur:
                logger.info("改为主动打开添加页: %s", cfg["add_multi_attr_url"])
                driver.get(cfg["add_multi_attr_url"])

        wait.until(
            lambda d: (
                "addMultiAttr" in (d.current_url or "")
                or len(d.find_elements(By.XPATH, "//input[contains(@placeholder,'SPU')]")) > 0
                or len(d.find_elements(By.XPATH, "//input[contains(@placeholder,'请输入SPU')]")) > 0
            )
        )
        save_shot(driver, "sellfox_multi_attr_add_page.png")

        ensure_add_page_context(driver)
        fill_basic_info(driver, cfg)
        ensure_tall_viewport_for_attr_dropdowns(driver, cfg)

        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located(
                (By.XPATH, "//input[contains(@placeholder,'请选择属性')]")
            )
        )

        attrs = [cfg["attr_1"], cfg["attr_2"], cfg["attr_3"]]
        for idx, attr_name in enumerate(attrs):
            selects = list_attr_selects(driver)
            if idx >= len(selects):
                save_shot(driver, "sellfox_multi_attr_selects_short.png")
                raise RuntimeError(
                    f"第 {idx + 1} 个属性行未就绪（当前仅 {len(selects)} 个「请选择属性」下拉）"
                )
            logger.info("选择第 %s 个属性: %s", idx + 1, attr_name)
            el_select_pick_option(driver, selects[idx], attr_name)
            if idx < len(attrs) - 1:
                click_add_attribute_row(driver)
                need = idx + 2
                WebDriverWait(driver, 12).until(
                    lambda d, n=need: len(list_attr_selects(d)) >= n
                )

        save_shot(driver, "sellfox_multi_attr_done.png")
        logger.info("已完成 SPU/款名与三个属性；浏览器保持打开，等待后续操作…")

        block = int(cfg.get("block_seconds") or 0)
        if block > 0:
            logger.info("SELLFOX_BLOCK_SECONDS=%s，休眠结束", block)
            time.sleep(block)
        else:
            if cfg.get("auto_quit_browser", True):
                input("按 Enter 关闭浏览器并结束脚本…")
            else:
                input(
                    "SELLFOX_AUTO_QUIT=false：按 Enter 仅结束脚本进程（浏览器保持打开，可继续手动操作）…"
                )

        return True

    except Exception as e:
        logger.error("流程异常: %s", e)
        logger.error(traceback.format_exc())
        save_shot(driver, "sellfox_multi_attr_error.png")
        return False

    finally:
        if sf.driver and cfg.get("auto_quit_browser", True):
            try:
                sf.driver.quit()
            except Exception as e:
                logger.warning("关闭浏览器: %s", e)
            sf.driver = None
        elif sf.driver and not cfg.get("auto_quit_browser", True):
            logger.info("已保留浏览器会话（SELLFOX_AUTO_QUIT=false），未调用 quit")


def main():
    ok = run_flow()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
