# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.1](https://github.com/billyjbryant/mcp-foxxy-bridge/compare/v1.1.0...v1.1.1) (2025-07-29)


### 🐛 Bug Fixes

* use release artifacts for PyPI publishing instead of rebuilding ([8ea1f9a](https://github.com/billyjbryant/mcp-foxxy-bridge/commit/8ea1f9a507d3e71ee54e855430c8c09a924acf78))

## [1.1.0](https://github.com/billyjbryant/mcp-foxxy-bridge/compare/v1.0.1...v1.1.0) (2025-07-29)


### 🚀 Features

* Enhanced Health Checks with Keep-Alive and Auto-Restart ([#4](https://github.com/billyjbryant/mcp-foxxy-bridge/issues/4)) ([660e0e2](https://github.com/billyjbryant/mcp-foxxy-bridge/commit/660e0e22ae15b224f115de7e6cb3b4cb06410ea7))


### 📚 Documentation

* updated the readme ([#2](https://github.com/billyjbryant/mcp-foxxy-bridge/issues/2)) ([4672644](https://github.com/billyjbryant/mcp-foxxy-bridge/commit/467264425321594c161a5e98a9c8f895ae05a7fd))

## [1.0.1](https://github.com/billyjbryant/mcp-foxxy-bridge/compare/v1.0.0...v1.0.1) (2025-07-27)


### 🐛 Bug Fixes

* remove Docker Hub publishing to resolve authentication error ([073701c](https://github.com/billyjbryant/mcp-foxxy-bridge/commit/073701ccffd6a0f2a7001ca662e856b33201b856))

## 1.0.0 (2025-07-27)


### 🚀 Features

* add CODEOWNERS file and improve PR validation workflow ([3100f27](https://github.com/billyjbryant/mcp-foxxy-bridge/commit/3100f2790efa88c1d30e318fbf87714c94732974))
* add functionality to start an SSE server to proxy a local stdio server ([#11](https://github.com/billyjbryant/mcp-foxxy-bridge/issues/11)) ([1b9880b](https://github.com/billyjbryant/mcp-foxxy-bridge/commit/1b9880bc5680c25bd42a096ebbfc65442154d19d))
* add support for SSE level authentication ([#2](https://github.com/billyjbryant/mcp-foxxy-bridge/issues/2)) ([abfb250](https://github.com/billyjbryant/mcp-foxxy-bridge/commit/abfb250e8b2281c5efb2076cdd946253bf48bd46))
* Allow passing through all environment variables to server ([#27](https://github.com/billyjbryant/mcp-foxxy-bridge/issues/27)) ([cc8a4fa](https://github.com/billyjbryant/mcp-foxxy-bridge/commit/cc8a4fac871fe89a214c09aeea6ca0ca98eea4fc))
* comprehensive project overhaul with semantic release and automation ([9575ed1](https://github.com/billyjbryant/mcp-foxxy-bridge/commit/9575ed1c813864c7034e5ee698a894cea446a0a1))
* comprehensive project overhaul with semantic release and automation ([#1](https://github.com/billyjbryant/mcp-foxxy-bridge/issues/1)) ([11fad75](https://github.com/billyjbryant/mcp-foxxy-bridge/commit/11fad75e90b4a3964aad0cf7672b7da5f1f0eb19))
* connect to remote servers with SSE ([6584ed4](https://github.com/billyjbryant/mcp-foxxy-bridge/commit/6584ed47c692f8305ef0f268a9e5b31699d5cce3))
* expose CORS configuration ([#31](https://github.com/billyjbryant/mcp-foxxy-bridge/issues/31)) ([209268a](https://github.com/billyjbryant/mcp-foxxy-bridge/commit/209268a361074876e44417d11da87790de03ca85))
* implement complete TODO functionality and fix repository corruption ([83522cd](https://github.com/billyjbryant/mcp-foxxy-bridge/commit/83522cdb9751ac24956a89261ee60152b2dd8dae))
* print version ([#93](https://github.com/billyjbryant/mcp-foxxy-bridge/issues/93)) ([e8ad1a0](https://github.com/billyjbryant/mcp-foxxy-bridge/commit/e8ad1a0b9dd4793c1befe1633b098df1c1165ce2))
* serve a SSE server proxying a STDIO server ([#8](https://github.com/billyjbryant/mcp-foxxy-bridge/issues/8)) ([44b09ec](https://github.com/billyjbryant/mcp-foxxy-bridge/commit/44b09ec9547088c7ea754c6356af005c84ee2016))
* simplify CODEOWNERS configuration for streamlined review process ([9abd444](https://github.com/billyjbryant/mcp-foxxy-bridge/commit/9abd444bafb9a3dd9a33bd0c793fa58b12ef744e))
* support --debug argument for verbose output ([#47](https://github.com/billyjbryant/mcp-foxxy-bridge/issues/47)) ([357c8c2](https://github.com/billyjbryant/mcp-foxxy-bridge/commit/357c8c23f0d64ba2d9fddd1a7d3db8f4d3898a5c)), closes [#34](https://github.com/billyjbryant/mcp-foxxy-bridge/issues/34)
* support 'headers' argument for SSE server connection ([#23](https://github.com/billyjbryant/mcp-foxxy-bridge/issues/23)) ([1de8394](https://github.com/billyjbryant/mcp-foxxy-bridge/commit/1de83947679136f5b0dd5a2c2e277a1b1f64853a))
* support env field in config file ([#79](https://github.com/billyjbryant/mcp-foxxy-bridge/issues/79)) ([cd13624](https://github.com/billyjbryant/mcp-foxxy-bridge/commit/cd13624f7b27ec00021e93de1271ce6d19ba5bf7))
* support multi-arch Docker image ([e6f9f3d](https://github.com/billyjbryant/mcp-foxxy-bridge/commit/e6f9f3db981b51a8d64289db8871358451424b5f))
* support passing 'stateless' and 'cwd' arguments ([#62](https://github.com/billyjbryant/mcp-foxxy-bridge/issues/62)) ([2980a50](https://github.com/billyjbryant/mcp-foxxy-bridge/commit/2980a50ad2e78ff8ba8c5ed2520ba16133c4f7bc))
* support proxying multiple MCP stdio servers to SSE ([#65](https://github.com/billyjbryant/mcp-foxxy-bridge/issues/65)) ([b25056f](https://github.com/billyjbryant/mcp-foxxy-bridge/commit/b25056faddfe452d2859c5d4e72233986a59e6a7))
* support streamable http proxy ([#60](https://github.com/billyjbryant/mcp-foxxy-bridge/issues/60)) ([8fee3d9](https://github.com/billyjbryant/mcp-foxxy-bridge/commit/8fee3d9833f66ca1c728fd68adad2c6e139e0499))
* support streamable transport in client mode ([#70](https://github.com/billyjbryant/mcp-foxxy-bridge/issues/70)) ([f31cd3e](https://github.com/billyjbryant/mcp-foxxy-bridge/commit/f31cd3e73c02264822e66af30feaf1bac66448b2))


### 🐛 Bug Fixes

* add COM812 to ruff ignore list to resolve formatter conflict ([649eb1b](https://github.com/billyjbryant/mcp-foxxy-bridge/commit/649eb1b0cf666e61d666e922aba8724dbc35af8b))
* add command shortcut ([c07d479](https://github.com/billyjbryant/mcp-foxxy-bridge/commit/c07d4792ca9813ff139078c4d8127709febfc7c6))
* add workflow permissions ([c1edc1f](https://github.com/billyjbryant/mcp-foxxy-bridge/commit/c1edc1fd290896a0eac28507d186c9483e6bfd72))
* annotate multi-arch image before pushing to ghcr ([b84e774](https://github.com/billyjbryant/mcp-foxxy-bridge/commit/b84e7745f5199dc47b78493e32928ec06b9f6a05))
* connect other github actions with mypy job ([#14](https://github.com/billyjbryant/mcp-foxxy-bridge/issues/14)) ([e095434](https://github.com/billyjbryant/mcp-foxxy-bridge/commit/e0954341a3664d82c2a9707ac33218e3b8d179e8))
* correct debug logging typo ([#68](https://github.com/billyjbryant/mcp-foxxy-bridge/issues/68)) ([27a1627](https://github.com/billyjbryant/mcp-foxxy-bridge/commit/27a16279efa6a2fca75be5b27a2424e6d0b1d2ec))
* correct JSON syntax error in semantic release configuration ([0304339](https://github.com/billyjbryant/mcp-foxxy-bridge/commit/03043395981ea3b552bff7d303b62edb3ac98f5f))
* disable redirect to trailing slashes ([#89](https://github.com/billyjbryant/mcp-foxxy-bridge/issues/89)) ([73d6d79](https://github.com/billyjbryant/mcp-foxxy-bridge/commit/73d6d79fb6a92fa6f79f7dcceab08f2f91d132a6))
* explicitly activate virtual environment in Docker entrypoint ([c072a3b](https://github.com/billyjbryant/mcp-foxxy-bridge/commit/c072a3bb09636695a97ef7d9b348f6f4ea3b2766))
* finalize Docker configuration for reliable module execution ([de93dd8](https://github.com/billyjbryant/mcp-foxxy-bridge/commit/de93dd87f5ab70b21d1a58e4f26e7e8627b03542))
* missing slash on SSE /messages path ([#71](https://github.com/billyjbryant/mcp-foxxy-bridge/issues/71)) ([90134a9](https://github.com/billyjbryant/mcp-foxxy-bridge/commit/90134a9206cebe2aa011ea3d8574daaf0213b38c))
* nonetype is not callable ([#92](https://github.com/billyjbryant/mcp-foxxy-bridge/issues/92)) ([5f1d4de](https://github.com/billyjbryant/mcp-foxxy-bridge/commit/5f1d4de9e6f78faae3e1ba50634f640f2a893f1b))
* repair broken Python symlinks in virtual environment ([6c6cf16](https://github.com/billyjbryant/mcp-foxxy-bridge/commit/6c6cf16f5e05ad8151f3ff495b2fa40e8e8acacf))
* resolve all GitHub Actions workflow failures ([4d94be7](https://github.com/billyjbryant/mcp-foxxy-bridge/commit/4d94be79be30f1083b37f6504d281194fa05bdff))
* resolve all ruff linting errors and enhance pre-commit setup ([1b9d93a](https://github.com/billyjbryant/mcp-foxxy-bridge/commit/1b9d93accdb8c7df0ca251ae0d781f864a434f6e))
* resolve critical workflow failures ([827bd6f](https://github.com/billyjbryant/mcp-foxxy-bridge/commit/827bd6fbc625bc748f475d94ca34ed96ca60ada8))
* resolve GitHub Actions workflow failures ([8d0d714](https://github.com/billyjbryant/mcp-foxxy-bridge/commit/8d0d714396d7699b2a6371883200df76989a89c0))
* resolve remaining GitHub Actions workflow failures ([69e9a88](https://github.com/billyjbryant/mcp-foxxy-bridge/commit/69e9a88024cd1b6bda284b4be92b85e0af568a27))
* resolve test failures and version configuration ([323c492](https://github.com/billyjbryant/mcp-foxxy-bridge/commit/323c49297116356933a990f081fd02cc9779e905))
* resolve test-docker and validate-pr workflow failures ([06b10b1](https://github.com/billyjbryant/mcp-foxxy-bridge/commit/06b10b145e8094619c1392798a2fe9bf2700055b))
* resolve workflow failures and add comprehensive pre-commit hooks ([404eb1b](https://github.com/billyjbryant/mcp-foxxy-bridge/commit/404eb1ba4299f5344293b2a888ad867750df3037))
* use installed console script for Docker entrypoint ([88a6802](https://github.com/billyjbryant/mcp-foxxy-bridge/commit/88a6802976e066996b7e63e850d65cfe1b53c125))
* use virtual environment python in Docker entrypoint ([98d3e6c](https://github.com/billyjbryant/mcp-foxxy-bridge/commit/98d3e6cdf57a0c83bb0d8101913325ffe3f83848))


### 📚 Documentation

* mention pypi package ([#10](https://github.com/billyjbryant/mcp-foxxy-bridge/issues/10)) ([1b5b05b](https://github.com/billyjbryant/mcp-foxxy-bridge/commit/1b5b05b1ea276611d2beba51f8a4842f94242050))
* notes on docker-compose use ([78783f3](https://github.com/billyjbryant/mcp-foxxy-bridge/commit/78783f3aec988c04874b6dea81979e372a3818e4))
* readme correction ([da9cbf7](https://github.com/billyjbryant/mcp-foxxy-bridge/commit/da9cbf7386bee55b5325eabb888a26f936d35d12))
* README updates on --env ([6a888cb](https://github.com/billyjbryant/mcp-foxxy-bridge/commit/6a888cbe09913639299ac41b0118fc6cb432af3f))
* update documentation with workflow status ([f54a9cd](https://github.com/billyjbryant/mcp-foxxy-bridge/commit/f54a9cd8dcc1401ebba9a21c9344fd1afbef5fa2))
* update readme and --help output ([#13](https://github.com/billyjbryant/mcp-foxxy-bridge/issues/13)) ([874ae38](https://github.com/billyjbryant/mcp-foxxy-bridge/commit/874ae38087d8d7bf02e6af7db52d55a087fe572d))
* update README on how to use container ([b56e574](https://github.com/billyjbryant/mcp-foxxy-bridge/commit/b56e574cd90f9de8da7f80a119b096322f678ecd))
* use latest tag ([b4f3533](https://github.com/billyjbryant/mcp-foxxy-bridge/commit/b4f35330f0f80c660d83b60efddc26ee71ea1d0a))
