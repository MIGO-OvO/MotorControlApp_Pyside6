"""
PID优化器功能完整性测试
"""
import sys
import os

# 添加项目路径
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

def test_imports():
    """测试所有导入"""
    print("=" * 60)
    print("测试1: 模块导入")
    print("=" * 60)
    
    try:
        from src.core.pid_optimizer import (
            PatternSearchOptimizer, 
            PIDParams, 
            TestResult, 
            OptimizationRecord,
            OptimizerState,
            parse_test_result_packet,
            parse_test_result_text
        )
        print("✓ pid_optimizer 模块导入成功")
    except Exception as e:
        print(f"✗ pid_optimizer 模块导入失败: {e}")
        return False
    
    try:
        from src.ui.widgets import PIDOptimizerPanel
        print("✓ PIDOptimizerPanel 组件导入成功")
    except Exception as e:
        print(f"✗ PIDOptimizerPanel 组件导入失败: {e}")
        return False
    
    try:
        from src.ui.main_window_complete import MotorControlApp
        print("✓ 主窗口导入成功")
    except Exception as e:
        print(f"✗ 主窗口导入失败: {e}")
        return False
    
    return True

def test_pid_params():
    """测试PID参数类"""
    print("\n" + "=" * 60)
    print("测试2: PIDParams 类功能")
    print("=" * 60)
    
    from src.core.pid_optimizer import PIDParams
    
    # 创建参数
    params = PIDParams(Kp=0.14, Ki=0.015, Kd=0.06)
    print(f"✓ 创建参数: Kp={params.Kp}, Ki={params.Ki}, Kd={params.Kd}")
    
    # 生成指令
    cmd = params.to_command()
    print(f"✓ 生成指令: {cmd.strip()}")
    
    # 转换为数组
    arr = params.to_array()
    print(f"✓ 转换为数组: {arr}")
    
    # 从数组创建
    params2 = PIDParams.from_array(arr)
    print(f"✓ 从数组创建: Kp={params2.Kp}, Ki={params2.Ki}, Kd={params2.Kd}")
    
    return True

def test_optimizer_creation():
    """测试优化器创建"""
    print("\n" + "=" * 60)
    print("测试3: PatternSearchOptimizer 创建")
    print("=" * 60)
    
    from src.core.pid_optimizer import PatternSearchOptimizer, PIDParams
    from PySide6.QtWidgets import QApplication
    
    # 创建QApplication（Qt组件需要）
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    
    try:
        optimizer = PatternSearchOptimizer()
        print("✓ 优化器创建成功")
        
        # 配置优化器
        optimizer.configure(
            test_motor='X',
            test_angle=45.0,
            test_runs=3,
            max_iterations=10
        )
        print("✓ 优化器配置成功")
        
        # 检查状态
        print(f"✓ 初始状态: {optimizer.state.value}")
        print(f"✓ 最大迭代: {optimizer.max_iterations}")
        print(f"✓ 测试角度: {optimizer.test_angle}°")
        
        return True
    except Exception as e:
        print(f"✗ 优化器创建失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_result_parsing():
    """测试结果解析"""
    print("\n" + "=" * 60)
    print("测试4: 测试结果解析")
    print("=" * 60)
    
    from src.core.pid_optimizer import parse_test_result_text
    
    # 测试文本格式解析
    test_line = "PIDTEST_RESULT:X,run=0,conv=1234,ovs=0.12,err=0.05,osc=1,smooth=85,score=82"
    result = parse_test_result_text(test_line)
    
    if result:
        print(f"✓ 解析成功:")
        print(f"  - 电机ID: {result.motor_id}")
        print(f"  - 轮次: {result.run_index}")
        print(f"  - 收敛时间: {result.convergence_time_ms}ms")
        print(f"  - 过冲: {result.max_overshoot}°")
        print(f"  - 最终误差: {result.final_error}°")
        print(f"  - 振荡次数: {result.oscillation_count}")
        print(f"  - 平滑度: {result.smoothness_score}")
        print(f"  - 总分: {result.total_score}")
        return True
    else:
        print("✗ 解析失败")
        return False

def test_ui_panel():
    """测试UI面板"""
    print("\n" + "=" * 60)
    print("测试5: PIDOptimizerPanel UI组件")
    print("=" * 60)
    
    from src.ui.widgets import PIDOptimizerPanel
    from PySide6.QtWidgets import QApplication
    
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    
    try:
        panel = PIDOptimizerPanel()
        print("✓ UI面板创建成功")
        
        # 检查组件
        print(f"✓ Kp输入框: {panel.kp_input.value()}")
        print(f"✓ Ki输入框: {panel.ki_input.value()}")
        print(f"✓ Kd输入框: {panel.kd_input.value()}")
        print(f"✓ 测试电机: {panel.motor_combo.currentText()}")
        print(f"✓ 测试角度: {panel.angle_input.value()}°")
        
        # 测试更新方法
        panel.update_progress(5, 10, "测试中...")
        print("✓ 进度更新方法正常")
        
        panel.update_score(75.5, 80.2)
        print("✓ 得分更新方法正常")
        
        return True
    except Exception as e:
        print(f"✗ UI面板测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_bayesian_optimizer_logic():
    """测试贝叶斯优化器逻辑"""
    print("\n" + "=" * 60)
    print("测试6: 贝叶斯优化算法逻辑")
    print("=" * 60)
    
    from src.core.pid_optimizer import (
        PatternSearchOptimizer, PIDParams, 
        OptimizationRecord, TestResult, NonlinearPenalty,
        SKOPT_AVAILABLE
    )
    import numpy as np
    from PySide6.QtWidgets import QApplication
    
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    
    try:
        optimizer = PatternSearchOptimizer()
        
        # 检查贝叶斯优化库是否可用
        if SKOPT_AVAILABLE:
            print("✓ scikit-optimize 库已安装")
        else:
            print("⚠ scikit-optimize 未安装，将使用随机搜索")
        
        # 测试参数边界
        bounds = optimizer.PARAM_BOUNDS
        print(f"✓ Kp边界: {bounds['Kp']}")
        print(f"✓ Ki边界: {bounds['Ki']}")
        print(f"✓ Kd边界: {bounds['Kd']}")
        
        # 测试非线性惩罚计算
        record = OptimizationRecord(
            params=PIDParams(0.14, 0.015, 0.06),
            test_results=[
                TestResult(motor_id=0, run_index=0, total_runs=3, 
                          convergence_time_ms=1000, max_overshoot=0.3,
                          final_error=0.05, oscillation_count=1, 
                          smoothness_score=85, total_score=80),
                TestResult(motor_id=0, run_index=1, total_runs=3,
                          convergence_time_ms=1100, max_overshoot=0.4,
                          final_error=0.06, oscillation_count=2,
                          smoothness_score=82, total_score=78),
            ]
        )
        
        # 应用惩罚
        adjusted = NonlinearPenalty.apply_penalty(record)
        print(f"✓ 原始平均得分: {record.avg_score:.1f}")
        print(f"✓ 惩罚后得分: {adjusted:.1f}")
        print(f"✓ 最大过冲: {record.max_overshoot:.2f}°")
        print(f"✓ 收敛RSD: {record.convergence_rsd:.1f}%")
        
        # 测试高过冲惩罚（断崖式）
        record_high_overshoot = OptimizationRecord(
            params=PIDParams(0.20, 0.02, 0.04),
            test_results=[
                TestResult(motor_id=0, run_index=0, total_runs=1,
                          convergence_time_ms=800, max_overshoot=2.5,  # 高过冲
                          final_error=0.05, oscillation_count=3,
                          smoothness_score=70, total_score=75),
            ]
        )
        adjusted_high = NonlinearPenalty.apply_penalty(record_high_overshoot)
        penalty_ratio = adjusted_high / record_high_overshoot.avg_score
        print(f"✓ 高过冲(2.5°)惩罚: 得分从{record_high_overshoot.avg_score:.1f}降至{adjusted_high:.1f} (保留{penalty_ratio*100:.1f}%)")
        
        return True
    except Exception as e:
        print(f"✗ 贝叶斯优化逻辑测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def check_lower_device_code():
    """检查下位机代码完整性"""
    print("\n" + "=" * 60)
    print("测试7: 下位机代码完整性")
    print("=" * 60)
    
    cpp_file = "lowerDevice/src/main.cpp"
    
    if not os.path.exists(cpp_file):
        print(f"✗ 下位机代码文件不存在: {cpp_file}")
        return False
    
    with open(cpp_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 检查关键函数和结构
    checks = [
        ("PIDTestData", "测试数据结构"),
        ("parsePIDConfig", "PID参数配置解析"),
        ("parsePIDTest", "PID测试指令解析"),
        ("initPIDTest", "PID测试初始化"),
        ("runPIDTestSampling", "PID测试采样"),
        ("finishTestRun", "测试结果计算"),
        ("calculateSmoothnessScore", "平滑度评分"),
        ("calculateTotalScore", "综合评分"),
        ("computePIDWithSmoothing", "平滑PID控制"),
        ("PID_STARTUP_SPEED_RATIO", "中位速度启动"),
        ("PID_JERK_LIMIT", "加速度变化率限制"),
        ("PIDTestResultPacket", "测试结果数据包"),
    ]
    
    all_found = True
    for keyword, description in checks:
        if keyword in content:
            print(f"✓ {description}: {keyword}")
        else:
            print(f"✗ 缺失 {description}: {keyword}")
            all_found = False
    
    # 统计代码行数
    lines = content.split('\n')
    print(f"\n✓ 代码总行数: {len(lines)}")
    
    return all_found

def main():
    """主测试函数"""
    print("\n" + "=" * 60)
    print("PID参数优化器 - 功能完整性测试")
    print("=" * 60)
    
    results = []
    
    # 运行所有测试
    results.append(("模块导入", test_imports()))
    results.append(("PIDParams类", test_pid_params()))
    results.append(("优化器创建", test_optimizer_creation()))
    results.append(("结果解析", test_result_parsing()))
    results.append(("UI面板", test_ui_panel()))
    results.append(("贝叶斯优化", test_bayesian_optimizer_logic()))
    results.append(("下位机代码", check_lower_device_code()))
    
    # 汇总结果
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    
    passed = 0
    failed = 0
    
    for name, result in results:
        status = "✓ 通过" if result else "✗ 失败"
        print(f"{name:20s} : {status}")
        if result:
            passed += 1
        else:
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"总计: {passed} 通过, {failed} 失败")
    print("=" * 60)
    
    if failed == 0:
        print("\n🎉 所有测试通过！功能实现完整。")
        return 0
    else:
        print(f"\n⚠️  有 {failed} 项测试失败，请检查。")
        return 1

if __name__ == "__main__":
    sys.exit(main())
