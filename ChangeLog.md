# ChangeLog

## 最新提交 (2026-04-02): Add write-file validation

新增了文件写入验证功能，增强了对 `WriteFile` 工具的安全性检查：

- **新增文件**: `src/kimi_cli/tools/file/check_fmt.py`
  - 实现了文件格式验证逻辑，共 49 行代码
  - 确保写入的文件内容符合预期格式
  
- **更新文件**: `src/kimi_cli/tools/file/write.py`
  - 集成了验证机制，共新增 16 行代码
  - 在写入文件前进行有效性检查，防止损坏文件

这些改动提升了文件操作的安全性，确保 AI 生成的代码在写入前经过验证。
