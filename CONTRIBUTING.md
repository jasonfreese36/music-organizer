# Contributing / 参与贡献

Thank you for helping improve Music Organizer. Open an issue for a reproducible bug or send a focused pull request with a short explanation of the behavior being changed.

欢迎提交可复现的问题或范围明确的 PR，请说明具体触发条件与修改后的行为。

## Development

Follow the source setup in [README.md](README.md). Run the integration checks relevant to your changes using a fresh `test-output` subdirectory. The native reader has vendored dependencies and tests under `native/platformaudio`.

- Preserve the read-only source-library behavior and independent source/destination validation.
- Keep media payload verification and exclusive/atomic output handling.
- Match encrypted formats against public specifications or licensed references. Add independent vectors or generated fixtures; do not guess an algorithm based on an extension.
- Add new user-facing options under Advanced settings and retain conservative defaults.
- Update both project READMEs when support, setup or limitations change.
- Record upstream provenance and retain the appropriate notices for third-party code.

Use generated fixtures for reports and pull requests. Do not include personal music, real local key files, account databases, access tokens or identifying logs in a public contribution.

请保持源目录只读、音频校验和暂存后发布的处理方式。新增功能、支持范围、构建方法或限制变化时同步更新中英文说明；引入第三方实现时保留原许可证与来源。公开贡献使用生成样本，避免包含个人曲库、密钥、账号数据库或令牌。

## Licensing

Original project code is MIT-licensed. Contributions of original code are made under that license unless a file explicitly states a retained third-party license. Runtime dependencies and bundled programs keep their own terms; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
