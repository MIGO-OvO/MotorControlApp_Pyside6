"""
基础模块测试
验证重构后的模块是否正常工作
"""
import sys
import os

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)


def test_imports():
    """测试所有模块是否可以正常导入"""
    print("测试模块导入...")
    
    try:
        from src.config.constants import MOTOR_NAMES, APP_NAME
        print("[OK] 配置模块导入成功")
        
        from src.config.settings import SettingsManager
        print("[OK] 设置管理器导入成功")
        
        from src.core.serial_manager import SerialManager
        print("[OK] 串口管理器导入成功")
        
        from src.core.preset_manager import PresetManager
        print("[OK] 预设管理器导入成功")
        
        from src.core.command_generator import CommandGenerator
        print("[OK] 指令生成器导入成功")
        
        from src.core.automation_engine import AutomationThread
        print("[OK] 自动化引擎导入成功")
        
        from src.hardware.serial_reader import SerialReader
        print("[OK] 串口读取线程导入成功")
        
        from src.hardware.daq_thread import DAQThread
        print("[OK] DAQ线程导入成功")
        
        from src.ui.widgets import IOSSwitch, MotorCircle
        print("[OK] UI控件导入成功")
        
        from src.utils.logger import Logger
        print("[OK] 日志工具导入成功")
        
        from src.utils.data_handler import DataHandler
        print("[OK] 数据处理工具导入成功")
        
        print("\n所有模块导入测试通过！[PASS]")
        return True
        
    except ImportError as e:
        print(f"\n模块导入失败: {e} [FAIL]")
        return False


def test_serial_manager():
    """测试串口管理器基本功能"""
    print("\n测试串口管理器...")
    
    try:
        from src.core.serial_manager import SerialManager
        
        manager = SerialManager()
        ports = manager.get_available_ports()
        print(f"[OK] 找到 {len(ports)} 个可用串口: {', '.join(ports)}")
        
        print("串口管理器测试通过！[PASS]")
        return True
        
    except Exception as e:
        print(f"串口管理器测试失败: {e} [FAIL]")
        return False


def test_preset_manager():
    """测试预设管理器基本功能"""
    print("\n测试预设管理器...")
    
    try:
        from src.core.preset_manager import PresetManager
        
        manager = PresetManager()
        manual_presets = manager.get_manual_preset_names()
        auto_presets = manager.get_auto_preset_names()
        
        print(f"[OK] 找到 {len(manual_presets)} 个手动预设")
        print(f"[OK] 找到 {len(auto_presets)} 个自动预设")
        
        print("预设管理器测试通过！[PASS]")
        return True
        
    except Exception as e:
        print(f"预设管理器测试失败: {e} [FAIL]")
        return False


def test_command_generator():
    """测试指令生成器基本功能"""
    print("\n测试指令生成器...")
    
    try:
        from src.core.command_generator import CommandGenerator
        
        generator = CommandGenerator()
        
        # 测试简单指令生成
        test_params = {
            "X": {"enable": "E", "direction": "F", "speed": "10", "angle": "90"},
            "Y": {"enable": "D", "direction": "F", "speed": "0", "angle": "0"},
            "Z": {"enable": "D", "direction": "F", "speed": "0", "angle": "0"},
            "A": {"enable": "D", "direction": "F", "speed": "0", "angle": "0"}
        }
        
        command = generator.generate_command(test_params, "manual")
        print(f"[OK] 生成指令: {command.strip()}")
        
        # 测试停止指令
        stop_command = generator.generate_stop_command()
        print(f"[OK] 停止指令: {stop_command.strip()}")
        
        print("指令生成器测试通过！[PASS]")
        return True
        
    except Exception as e:
        print(f"指令生成器测试失败: {e} [FAIL]")
        return False


def test_settings_manager():
    """测试设置管理器基本功能"""
    print("\n测试设置管理器...")
    
    try:
        from src.config.settings import SettingsManager
        
        manager = SettingsManager("data/test_settings.json")
        
        # 测试设置
        manager.set("test.key", "test_value")
        value = manager.get("test.key")
        assert value == "test_value", "设置值不匹配"
        print("[OK] 设置存取正常")
        
        # 测试保存和加载
        manager.save()
        print("[OK] 设置保存成功")
        
        new_manager = SettingsManager("data/test_settings.json")
        new_manager.load()
        new_value = new_manager.get("test.key")
        assert new_value == "test_value", "加载的设置值不匹配"
        print("[OK] 设置加载成功")
        
        # 清理测试文件
        import os
        if os.path.exists("data/test_settings.json"):
            os.remove("data/test_settings.json")
        
        print("设置管理器测试通过！[PASS]")
        return True
        
    except Exception as e:
        print(f"设置管理器测试失败: {e} [FAIL]")
        return False


def main():
    """运行所有测试"""
    print("=" * 60)
    print("开始测试重构后的模块")
    print("=" * 60)
    
    results = []
    
    results.append(("模块导入", test_imports()))
    results.append(("串口管理器", test_serial_manager()))
    results.append(("预设管理器", test_preset_manager()))
    results.append(("指令生成器", test_command_generator()))
    results.append(("设置管理器", test_settings_manager()))
    
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    
    for name, passed in results:
        status = "[PASS]" if passed else "[FAIL]"
        print(f"{name}: {status}")
    
    all_passed = all(result[1] for result in results)
    
    print("\n" + "=" * 60)
    if all_passed:
        print("所有测试通过！")
    else:
        print("部分测试失败，请检查错误信息。")
    print("=" * 60)
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())

