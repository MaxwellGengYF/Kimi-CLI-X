import argparse
import subprocess
import shutil
import sys
from pathlib import Path


CURRENT_ROOT = Path(__file__).parent.resolve()
DIST_DIR = CURRENT_ROOT / "dist"


def confirm_step(step_name: str, package_name: str) -> bool:
    """询问用户是否执行此步骤"""
    msg = f"\n【{package_name}】是否需要执行: {step_name}? [y/N]: "
    ans = input(msg).strip().lower()
    return ans in ("y", "yes")


def run_cmd(cmd: list[str], cwd: str | None = None) -> int:
    """运行命令并实时输出"""
    print(f">>> 执行命令: {' '.join(cmd)} (cwd={cwd or '.'})")
    result = subprocess.run(cmd, cwd=cwd)
    return result.returncode


def delete_dist() -> bool:
    """删除 dist 目录"""
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
        print(f"已删除 {DIST_DIR}")
    else:
        print(f"{DIST_DIR} 不存在，无需删除")
    return True


def build_package(cwd: str | None = None) -> int:
    """运行 uv build"""
    return run_cmd(["uv", "build", "--out-dir", str(DIST_DIR)], cwd=cwd)


def publish_package(token: str) -> int:
    """运行 uv publish"""
    return run_cmd(["uv", "publish", f"--token={token}"], cwd=str(CURRENT_ROOT))


def process_package(name: str, cwd: str | None, token: str) -> bool:
    """
    处理单个包的发布流程
    返回 False 表示用户选择跳过此包
    """
    # 步骤1: 确认是否删除 dist
    if not confirm_step("删除 dist 目录", name):
        print(f"跳过包: {name}")
        return False
    delete_dist()

    # 步骤2: 确认是否构建
    if not confirm_step("uv build 构建", name):
        print(f"跳过包: {name}")
        return False
    if build_package(cwd) != 0:
        print(f"构建失败: {name}")
        sys.exit(1)

    # 步骤3: 确认是否发布
    if not confirm_step("uv publish 发布", name):
        print(f"跳过包: {name}")
        return False
    if publish_package(token) != 0:
        print(f"发布失败: {name}")
        sys.exit(1)

    print(f"\n✅ {name} 处理完成！")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="发布 Python 包工具")
    parser.add_argument("--token", required=True, help="PyPI/仓库的发布 token")
    args = parser.parse_args()
    token = args.token

    # 定义三个包及其工作目录
    packages = [
        ("kosong-x", "kimi-cli\\packages\\kosong"),
        ("kimi-cli-x", "kimi-cli"),
        ("kimi-agent-sdk-x", "kimi-agent-sdk\\python"),
        ("根项目", None),
    ]

    for name, cwd in packages:
        # 处理每个包，如果用户选择跳过则继续下一个
        process_package(name, cwd, token)

    print("\n🎉 所有包处理完毕！")


if __name__ == "__main__":
    main()
