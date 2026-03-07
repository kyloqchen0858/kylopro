import sys

def greet(name="World"):
    """向指定名称发送问候"""
    return f"Hello, {name}!"

def main():
    # 检查命令行参数
    if len(sys.argv) > 1:
        name = " ".join(sys.argv[1:])  # 支持多单词名称
    else:
        name = "World"
    
    # 打印问候语
    print(greet(name))

if __name__ == "__main__":
    print("Hello from Kylopro!")
    main()