import os
import sys
import subprocess
import tempfile
import unittest

class TestEncoding(unittest.TestCase):
    """测试编码修复效果"""

    def test_chinese_file_read_write(self):
        """测试中文文件读写"""
        # 准备包含中文的测试内容
        test_content = "你好，世界！\n这是一段包含中文的测试文本。\nHello, World!"
        
        # 创建临时文件
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', suffix='.txt', delete=False) as f:
            temp_file = f.name
            f.write(test_content)
        
        try:
            # 读取文件内容
            with open(temp_file, 'r', encoding='utf-8') as f:
                read_content = f.read()
            
            # 验证读取的内容与写入的内容一致
            self.assertEqual(test_content, read_content, "文件读写内容不一致")
            
            # 测试追加写入
            append_content = "\n追加的中文内容：测试完成！"
            with open(temp_file, 'a', encoding='utf-8') as f:
                f.write(append_content)
            
            # 再次读取验证
            with open(temp_file, 'r', encoding='utf-8') as f:
                final_content = f.read()
            
            self.assertEqual(test_content + append_content, final_content, "追加写入内容不一致")
            
        finally:
            # 清理临时文件
            if os.path.exists(temp_file):
                os.unlink(temp_file)

    def test_console_output(self):
        """测试控制台输出"""
        # 测试标准输出
        test_output = "控制台输出测试：中文测试文本"
        
        # 这里我们无法直接捕获print的输出进行断言，但可以验证字符串本身
        # 在实际测试中，可以通过重定向sys.stdout来捕获输出
        import io
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        
        try:
            print(test_output)
            captured = sys.stdout.getvalue().strip()
            self.assertEqual(test_output, captured, "控制台输出内容不一致")
        finally:
            sys.stdout = old_stdout
        
        # 测试错误输出
        sys.stderr = io.StringIO()
        try:
            print(test_output, file=sys.stderr)
            captured_err = sys.stderr.getvalue().strip()
            self.assertEqual(test_output, captured_err, "控制台错误输出内容不一致")
        finally:
            sys.stderr = sys.__stderr__

    def test_subprocess_execution(self):
        """测试子进程执行"""
        # 测试执行包含中文输出的命令
        test_script = """
import sys
print("子进程中文输出：测试成功！")
sys.stdout.flush()
"""
        
        # 创建临时Python脚本
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', suffix='.py', delete=False) as f:
            script_file = f.name
            f.write(test_script)
        
        try:
            # 执行子进程
            result = subprocess.run(
                [sys.executable, script_file],
                capture_output=True,
                text=True,
                encoding='utf-8'
            )
            
            # 验证子进程执行成功
            self.assertEqual(result.returncode, 0, "子进程执行失败")
            
            # 验证输出包含预期中文
            expected_output = "子进程中文输出：测试成功！"
            self.assertIn(expected_output, result.stdout.strip(), "子进程输出不包含预期中文")
            
            # 测试包含中文参数的命令
            chinese_arg = "中文参数测试"
            test_script_arg = """
import sys
if len(sys.argv) > 1:
    print(f"收到参数: {sys.argv[1]}")
"""
            
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', suffix='.py', delete=False) as f:
                script_file_arg = f.name
                f.write(test_script_arg)
            
            try:
                result = subprocess.run(
                    [sys.executable, script_file_arg, chinese_arg],
                    capture_output=True,
                    text=True,
                    encoding='utf-8'
                )
                
                self.assertEqual(result.returncode, 0, "带中文参数的子进程执行失败")
                self.assertIn(chinese_arg, result.stdout.strip(), "子进程未正确处理中文参数")
                
            finally:
                if os.path.exists(script_file_arg):
                    os.unlink(script_file_arg)
                    
        finally:
            # 清理临时文件
            if os.path.exists(script_file):
                os.unlink(script_file)

    def test_encoding_detection(self):
        """测试编码检测"""
        # 测试不同编码的文件
        test_content = "编码测试：中文文本"
        
        # UTF-8 编码
        with tempfile.NamedTemporaryFile(mode='wb', suffix='_utf8.txt', delete=False) as f:
            utf8_file = f.name
            f.write(test_content.encode('utf-8'))
        
        # GBK 编码
        with tempfile.NamedTemporaryFile(mode='wb', suffix='_gbk.txt', delete=False) as f:
            gbk_file = f.name
            f.write(test_content.encode('gbk'))
        
        try:
            # 用正确编码读取UTF-8文件
            with open(utf8_file, 'r', encoding='utf-8') as f:
                utf8_content = f.read()
            self.assertEqual(test_content, utf8_content, "UTF-8编码读取失败")
            
            # 用正确编码读取GBK文件
            with open(gbk_file, 'r', encoding='gbk') as f:
                gbk_content = f.read()
            self.assertEqual(test_content, gbk_content, "GBK编码读取失败")
            
            # 测试错误编码的情况（应该抛出异常或得到乱码）
            with self.assertRaises(UnicodeDecodeError):
                with open(gbk_file, 'r', encoding='utf-8') as f:
                    f.read()
                    
        finally:
            # 清理临时文件
            for f in [utf8_file, gbk_file]:
                if os.path.exists(f):
                    os.unlink(f)

    def test_environment_variables(self):
        """测试环境变量中的中文"""
        # 设置包含中文的环境变量
        chinese_env = "测试环境变量值"
        os.environ['TEST_CHINESE_ENV'] = chinese_env
        
        # 验证可以正确读取
        self.assertEqual(os.environ.get('TEST_CHINESE_ENV'), chinese_env, 
                        "环境变量中的中文读取失败")
        
        # 测试子进程读取环境变量
        test_script = """
import os
print(os.environ.get('TEST_CHINESE_ENV', ''))
"""
        
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', suffix='.py', delete=False) as f:
            script_file = f.name
            f.write(test_script)
        
        try:
            result = subprocess.run(
                [sys.executable, script_file],
                capture_output=True,
                text=True,
                encoding='utf-8',
                env=os.environ  # 传递当前环境变量
            )
            
            self.assertEqual(result.returncode, 0, "环境变量测试子进程执行失败")
            self.assertEqual(chinese_env, result.stdout.strip(), 
                           "子进程读取环境变量中的中文失败")
            
        finally:
            if os.path.exists(script_file):
                os.unlink(script_file)
            # 清理环境变量
            if 'TEST_CHINESE_ENV' in os.environ:
                del os.environ['TEST_CHINESE_ENV']

if __name__ == '__main__':
    unittest.main()