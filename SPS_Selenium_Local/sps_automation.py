#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SPS Commerce Selenium 自动化脚本
从 Deepnote Jupyter notebook 转换而来
用于每天自动发送 Inventory Advice
"""

import os
import time
import logging
import traceback
from datetime import datetime, timedelta
# Windows 兼容的时区处理
try:
    from zoneinfo import ZoneInfo
    # 测试是否可以使用 Asia/Shanghai
    try:
        test_tz = ZoneInfo("Asia/Shanghai")
        USE_ZONEINFO = True
    except Exception:
        USE_ZONEINFO = False
except ImportError:
    USE_ZONEINFO = False

if not USE_ZONEINFO:
    # 如果 zoneinfo 不可用，使用简单的 UTC+8 偏移
    from datetime import timezone, timedelta
    SHANGHAI_TZ = timezone(timedelta(hours=8))
from selenium.common.exceptions import NoSuchElementException, TimeoutException, WebDriverException
from selenium.webdriver import Chrome
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# 导入配置
from config import SPS_CONFIG

# 设置日志 - Windows 兼容版本
import os
os.makedirs('logs', exist_ok=True)  # 确保 logs 目录存在

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/sps_automation.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class SPSAutomation:
    def __init__(self):
        self.driver = None
        # Windows 兼容的时区设置
        if USE_ZONEINFO:
            self.tz_sh = ZoneInfo("Asia/Shanghai")
        else:
            self.tz_sh = SHANGHAI_TZ
    
    def cleanup_old_screenshots(self):
        """清理旧的截图文件"""
        try:
            screenshots_dir = 'screenshots'
            if not os.path.exists(screenshots_dir):
                logger.info("screenshots 目录不存在，无需清理")
                return True
            
            # 定义成功运行时的截图文件名列表
            success_screenshots = [
                'login_success.png',
                'create_new_doc.png', 
                'template_selected.png',
                'ia_number_filled.png',
                'inventory_advice_filled.png',
                'send_clicked.png',
                'first_continue.png',
                'second_continue.png',
                'automation_success.png'
            ]
            
            # 获取所有截图文件
            all_files = os.listdir(screenshots_dir)
            png_files = [f for f in all_files if f.lower().endswith('.png')]
            
            cleaned_count = 0
            for filename in png_files:
                filepath = os.path.join(screenshots_dir, filename)
                try:
                    # 删除文件
                    os.remove(filepath)
                    cleaned_count += 1
                    logger.info(f"已清理旧截图: {filename}")
                except Exception as e:
                    logger.warning(f"清理截图失败 {filename}: {e}")
            
            if cleaned_count > 0:
                logger.info(f"共清理了 {cleaned_count} 个旧截图文件")
            else:
                logger.info("没有需要清理的截图文件")
                
            return True
            
        except Exception as e:
            logger.error(f"清理旧截图时出错: {e}")
            return False
        
    def setup_driver(self):
        """设置 Chrome WebDriver"""
        try:
            options = Options()
            options.add_argument("--headless")  # 无头模式
            options.add_argument("--disable-gpu")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--window-size=1280,720")
            options.add_argument("--disable-extensions")
            options.add_argument("--disable-infobars")
            
            # Windows 版本：使用 webdriver-manager 自动管理 ChromeDriver
            try:
                from webdriver_manager.chrome import ChromeDriverManager
                chrome_service = Service(ChromeDriverManager().install())
                logger.info("使用 webdriver-manager 自动管理 ChromeDriver")
            except ImportError:
                logger.warning("webdriver-manager 未安装，尝试使用系统 ChromeDriver")
                chrome_service = Service()  # 使用系统 PATH 中的 chromedriver
            
            # 启动浏览器
            self.driver = Chrome(service=chrome_service, options=options)
            self.driver.implicitly_wait(30)
            
            logger.info("Chrome WebDriver 初始化成功")
            return True
            
        except Exception as e:
            logger.error(f"Chrome WebDriver 初始化失败: {e}")
            return False
    
    def get_timestamp_datestamp(self, timeform='%Y%m%d_%H%M%S', dateform='%m/%d/%Y', day_offset=7):
        """获取时间戳和日期戳"""
        now = datetime.now(self.tz_sh)
        timestamp = now.strftime(timeform)
        datestamp_offset = (now + timedelta(days=day_offset)).strftime(dateform)
        timestamp_prefix = f"{day_offset}_{timestamp}"
        return timestamp_prefix, datestamp_offset
    
    def save_screenshot(self, filename):
        """保存截图"""
        try:
            # 确保 screenshots 目录存在
            os.makedirs('screenshots', exist_ok=True)
            filepath = f"screenshots/{filename}"
            
            # 如果文件已存在，先删除以确保完全覆盖
            if os.path.exists(filepath):
                try:
                    os.remove(filepath)
                    logger.info(f"已删除旧截图: {filepath}")
                except Exception as e:
                    logger.warning(f"删除旧截图失败: {e}")
            
            # 保存新截图
            self.driver.save_screenshot(filepath)
            logger.info(f"截图已保存: {filepath}")
            
            # 验证文件是否成功保存
            if os.path.exists(filepath):
                file_size = os.path.getsize(filepath)
                logger.info(f"截图文件大小: {file_size} bytes")
                return filepath
            else:
                logger.error(f"截图保存失败，文件不存在: {filepath}")
                return None
                
        except Exception as e:
            logger.error(f"保存截图失败: {e}")
            return None
    
    def safe_find_element(self, by, value, timeout=30, description="元素"):
        """安全查找元素，带重试和详细日志"""
        try:
            logger.info(f"查找{description}: {value}")
            element = WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((by, value))
            )
            logger.info(f"成功找到{description}")
            return element
        except TimeoutException:
            logger.error(f"查找{description}超时: {value}")
            self.save_screenshot(f"element_not_found_{int(time.time())}.png")
            raise
        except Exception as e:
            logger.error(f"查找{description}时出错: {e}")
            self.save_screenshot(f"element_error_{int(time.time())}.png")
            raise
    
    def safe_click(self, element, description="元素"):
        """安全点击元素"""
        try:
            logger.info(f"点击{description}")
            # 等待元素可点击
            WebDriverWait(self.driver, 10).until(EC.element_to_be_clickable(element))
            element.click()
            logger.info(f"成功点击{description}")
            return True
        except Exception as e:
            logger.error(f"点击{description}失败: {e}")
            # 尝试使用 JavaScript 点击
            try:
                logger.info(f"尝试使用 JavaScript 点击{description}")
                self.driver.execute_script("arguments[0].click();", element)
                logger.info(f"JavaScript 点击{description}成功")
                return True
            except Exception as js_e:
                logger.error(f"JavaScript 点击{description}也失败: {js_e}")
                self.save_screenshot(f"click_failed_{int(time.time())}.png")
                return False
    
    def safe_send_keys(self, element, text, description="输入框"):
        """安全输入文本"""
        try:
            logger.info(f"向{description}输入文本")
            element.clear()
            time.sleep(2)
            element.send_keys(text)
            logger.info(f"成功向{description}输入文本")
            return True
        except Exception as e:
            logger.error(f"向{description}输入文本失败: {e}")
            self.save_screenshot(f"input_failed_{int(time.time())}.png")
            return False
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def login_sps(self):
        """登录 SPS Commerce"""
        try:
            logger.info("开始登录 SPS Commerce")
            
            # 访问登录页面
            link_sys = "https://commerce.spscommerce.com/fulfillment/transactions/list/"
            logger.info(f"访问登录页面: {link_sys}")
            self.driver.get(link_sys)
            time.sleep(SPS_CONFIG['page_load_wait'])
            
            # 输入邮箱
            xpath_email = "//input[@inputmode='email']"
            element_email = self.safe_find_element(By.XPATH, xpath_email, description="邮箱输入框")
            if not self.safe_send_keys(element_email, SPS_CONFIG['email'], "邮箱输入框"):
                raise Exception("输入邮箱失败")
            
            # 点击下一步
            xpath_btn_next = "//button[@type='submit']"
            btn_next = self.safe_find_element(By.XPATH, xpath_btn_next, description="下一步按钮")
            if not self.safe_click(btn_next, "下一步按钮"):
                raise Exception("点击下一步按钮失败")
            
            time.sleep(SPS_CONFIG['action_wait'])
            
            # 输入密码
            xpath_password = "//input[@id='password']"
            element_password = self.safe_find_element(By.XPATH, xpath_password, description="密码输入框")
            if not self.safe_send_keys(element_password, SPS_CONFIG['password'], "密码输入框"):
                raise Exception("输入密码失败")
            
            # 点击登录
            xpath_btn_login = "//button[@type='submit']"
            btn_login = self.safe_find_element(By.XPATH, xpath_btn_login, description="登录按钮")
            if not self.safe_click(btn_login, "登录按钮"):
                raise Exception("点击登录按钮失败")
            
            time.sleep(SPS_CONFIG['login_wait'])
            self.save_screenshot("login_success.png")
            logger.info("登录完成")
            return True
            
        except Exception as e:
            logger.error(f"登录失败: {e}")
            logger.error(f"错误详情: {traceback.format_exc()}")
            self.save_screenshot("login_error.png")
            raise
    
    def create_new_document(self):
        """创建新文档"""
        try:
            logger.info("开始创建新文档")
            
            # 跳出 iframe
            self.driver.switch_to.default_content()
            time.sleep(5)
            
            # 切换到第1个 iframe
            iframe = self.driver.find_elements(By.TAG_NAME, 'iframe')[0]
            self.driver.switch_to.frame(iframe)
            time.sleep(5)
            
            # 点击创建新文档按钮
            xpath_btn_create = "//div[@class='sps-button sps-button--confirm']"
            btn_create = self.driver.find_element(By.XPATH, xpath_btn_create)
            btn_create.click()
            
            time.sleep(30)
            self.save_screenshot("create_new_doc.png")
            logger.info("新文档创建按钮已点击")
            return True
            
        except Exception as e:
            logger.error(f"创建新文档失败: {e}")
            self.save_screenshot("create_doc_error.png")
            return False
    
    def select_partner_and_template(self):
        """选择合作伙伴和模板"""
        try:
            logger.info("开始选择合作伙伴和模板")
            
            # 选择合作伙伴下拉框
            xpath_dropdown_partner = "//span[@data-testid='createNewDocPartnerSelector-value']"
            dropdown_partner = self.driver.find_element(By.XPATH, xpath_dropdown_partner)
            dropdown_partner.click()
            time.sleep(10)
            
            # 选择 Williams Sonoma OSR
            xpath_select_partner = "//span[text()='Williams Sonoma OSR']"
            select_partner = self.driver.find_element(By.XPATH, xpath_select_partner)
            select_partner.click()
            time.sleep(10)
            
            # 勾选"没有源文档"
            xpath_no_source_doc = "//div[@data-testid='createNewDocSelectPartnerFormStepContainer']/div[@class='sps-form-group sps-checkbox sps-checkable']/label[@class='sps-checkable__label']"
            no_source_doc = self.driver.find_element(By.XPATH, xpath_no_source_doc)
            no_source_doc.click()
            time.sleep(10)
            
            # 选择使用现有模板
            xpath_use_template = "//div[@data-testid='createNewDocSelectTemplateStep']//div[@data-testid='createNewDocFromTemplate']/label[@class='sps-checkable__label']"
            use_template = self.driver.find_element(By.XPATH, xpath_use_template)
            use_template.click()
            time.sleep(10)
            
            # 打开模板下拉框
            xpath_dropdown_template = "//div[@data-testid='createNewDocSelectTemplateStep']//span[@data-testid='createNewDocTemplateSelector-value']"
            dropdown_template = self.driver.find_element(By.XPATH, xpath_dropdown_template)
            dropdown_template.click()
            time.sleep(10)
            
            # 根据日期选择模板
            if datetime.now(self.tz_sh) < datetime(2025, 10, 2, tzinfo=self.tz_sh):
                logger.info("使用 IA Template 20250925 0xBlack138 till1009")
                xpath_template = "//span[text()='IA Template 20250925 0xBlack138 till1009']"
            else:
                logger.info("使用 IA Template 20250605 x100")
                xpath_template = "//span[text()='IA Template 20250605 x100']"
            
            select_template = self.driver.find_element(By.XPATH, xpath_template)
            select_template.click()
            time.sleep(10)
            
            # 点击创建新 Inventory Advice
            xpath_btn_create_ia = "//div[@class='sps-modal__footer']/div[@class='sps-button sps-button--confirm']/button[@data-testid='modalOkBtn']"
            btn_create_ia = self.driver.find_element(By.XPATH, xpath_btn_create_ia)
            btn_create_ia.click()
            
            time.sleep(45)
            self.save_screenshot("template_selected.png")
            logger.info("合作伙伴和模板选择完成")
            return True
            
        except Exception as e:
            logger.error(f"选择合作伙伴和模板失败: {e}")
            self.save_screenshot("partner_template_error.png")
            return False
    
    def fill_inventory_advice(self):
        """填写 Inventory Advice 信息"""
        try:
            logger.info("开始填写 Inventory Advice 信息")
            
            # 切换到正确的 iframe
            self.driver.switch_to.default_content()
            time.sleep(5)
            iframe = self.driver.find_elements(By.TAG_NAME, 'iframe')[0]
            self.driver.switch_to.frame(iframe)
            time.sleep(5)
            
            # 获取时间戳和日期
            timestamp, datestamp = self.get_timestamp_datestamp()
            logger.info(f"时间戳: {timestamp}, 日期: {datestamp}")
            
            # 填写 IA 编号
            xpath_ia_number = "//input[@data-testid='inventoryAdvice.header.reference-input__input']"
            ia_number_input = self.driver.find_element(By.XPATH, xpath_ia_number)
            ia_number_input.clear()
            time.sleep(5)
            
            send_text_ia_number = f'IA{timestamp}'
            ia_number_input.send_keys(send_text_ia_number)
            time.sleep(5)
            
            self.save_screenshot("ia_number_filled.png")
            
            # 填写报告日期
            xpath_ia_date = "//input[@data-testid='inventoryAdvice.header.reportDate-input_date_input']"
            ia_date_input = self.driver.find_element(By.XPATH, xpath_ia_date)
            ia_date_input.clear()
            time.sleep(5)
            
            ia_date_input.send_keys(datestamp)
            ia_date_input.send_keys(Keys.TAB)
            time.sleep(3)
            
            # 再次清空并填写（确保格式正确）
            ia_date_input.clear()
            time.sleep(5)
            ia_date_input.send_keys(datestamp)
            time.sleep(5)
            
            self.save_screenshot("inventory_advice_filled.png")
            logger.info("Inventory Advice 信息填写完成")
            return True
            
        except Exception as e:
            logger.error(f"填写 Inventory Advice 信息失败: {e}")
            self.save_screenshot("fill_ia_error.png")
            return False
    
    def send_inventory_advice(self):
        """发送 Inventory Advice"""
        try:
            logger.info("开始发送 Inventory Advice")
            
            # 点击发送按钮
            xpath_btn_send = "//button[@data-testid='dataEntry_document-actions-send']"
            btn_send = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, xpath_btn_send))
            )
            btn_send.click()
            time.sleep(15)
            
            self.save_screenshot("send_clicked.png")
            
            # 处理第一个 Continue 按钮
            self.driver.switch_to.default_content()
            wait = WebDriverWait(self.driver, 10)
            iframe = wait.until(EC.presence_of_element_located((By.XPATH, "//iframe[@data-testid='app-frame']")))
            self.driver.switch_to.frame(iframe)
            
            xpath_btn_continue = "//button[@data-testid='modalOkBtn']"
            btn_continue = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, xpath_btn_continue))
            )
            self.driver.execute_script("arguments[0].click();", btn_continue)
            time.sleep(30)
            
            self.save_screenshot("first_continue.png")
            
            # 处理第二个 Continue 按钮（如果存在）
            try:
                self.driver.switch_to.default_content()
                iframe = wait.until(EC.presence_of_element_located((By.XPATH, "//iframe[@data-testid='app-frame']")))
                self.driver.switch_to.frame(iframe)
                
                btn_continue2 = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, xpath_btn_continue))
                )
                self.driver.execute_script("arguments[0].click();", btn_continue2)
                time.sleep(30)
                
                self.save_screenshot("second_continue.png")
            except TimeoutException:
                logger.info("没有找到第二个 Continue 按钮，继续执行")
            
            logger.info("Inventory Advice 发送完成")
            return True
            
        except Exception as e:
            logger.error(f"发送 Inventory Advice 失败: {e}")
            self.save_screenshot("send_error.png")
            return False
    
    def run_automation(self):
        """运行完整的自动化流程"""
        start_time = datetime.now(self.tz_sh)
        logger.info("=== SPS Selenium 自动化开始 ===")
        logger.info(f"开始时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        success = False
        error_details = None
        
        try:
            # 清理旧截图
            logger.info("步骤 0/6: 清理旧截图文件")
            self.cleanup_old_screenshots()
            
            # 初始化 WebDriver
            logger.info("步骤 1/6: 初始化 WebDriver")
            if not self.setup_driver():
                raise Exception("WebDriver 初始化失败")
            
            # 登录
            logger.info("步骤 2/6: 登录 SPS Commerce")
            self.login_sps()  # 使用重试装饰器
            
            # 创建新文档
            logger.info("步骤 3/6: 创建新文档")
            if not self.create_new_document():
                raise Exception("创建新文档失败")
            
            # 选择合作伙伴和模板
            logger.info("步骤 4/6: 选择合作伙伴和模板")
            if not self.select_partner_and_template():
                raise Exception("选择合作伙伴和模板失败")
            
            # 填写 Inventory Advice 信息
            logger.info("步骤 5/6: 填写 Inventory Advice 信息")
            if not self.fill_inventory_advice():
                raise Exception("填写 Inventory Advice 信息失败")
            
            # 发送 Inventory Advice
            logger.info("步骤 6/6: 发送 Inventory Advice")
            if not self.send_inventory_advice():
                raise Exception("发送 Inventory Advice 失败")
            
            success = True
            self.save_screenshot("automation_success.png")
            
        except Exception as e:
            error_details = str(e)
            logger.error(f"自动化流程出错: {e}")
            logger.error(f"错误详情: {traceback.format_exc()}")
            self.save_screenshot("automation_error.png")
            
        finally:
            # 清理资源
            if self.driver:
                try:
                    self.driver.quit()
                    logger.info("WebDriver 已关闭")
                except Exception as e:
                    logger.error(f"关闭 WebDriver 时出错: {e}")
            
            # 记录执行结果
            end_time = datetime.now(self.tz_sh)
            duration = end_time - start_time
            
            logger.info("=== SPS Selenium 自动化结束 ===")
            logger.info(f"结束时间: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info(f"执行时长: {duration}")
            
            if success:
                logger.info("✅ 自动化任务执行成功！")
            else:
                logger.error(f"❌ 自动化任务执行失败: {error_details}")
            
            return success

def main():
    """主函数"""
    automation = SPSAutomation()
    success = automation.run_automation()
    
    if success:
        logger.info("自动化任务执行成功")
        exit(0)
    else:
        logger.error("自动化任务执行失败")
        exit(1)

if __name__ == "__main__":
    main()
