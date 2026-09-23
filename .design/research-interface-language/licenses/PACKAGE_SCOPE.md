# 本包的代码与分发范围

本包用于将用户现有的 Research Systems 完整 HTML 应用，作为跨项目设计参考提供给 coding agent。没有将 React Bits 的各个组件拆成独立发行文件，也没有创建可销售的第三方动效组件库。

`assets/reference.html` 原样保留了 V9 的版权、完整许可文本及适配说明。`THIRD_PARTY_NOTICES.txt` 是从该应用提取的许可文本副本。参考中的 shader、部分动作机制与主机适配有不同来源；不能给整个包套上一个“全部 MIT”的标签。

React Bits 当前官方 LICENSE.md 对作为应用、网站或产品一部分的使用给出许可，并单列对组件自身单独、打包或移植后再分发的限制。Paper Shaders 的 LICENSE 为 Apache-2.0。相关代码按原许可处理；后续分发或出售应用时保留对应 notice，不能将本设计包理解成上游组件的再授权。

官方许可文本（2026-09-19 核对）：

- https://raw.githubusercontent.com/DavidHDev/react-bits/main/LICENSE.md
- https://raw.githubusercontent.com/paper-design/shaders/main/LICENSE

本包新增的文档、安装／校验脚本、命名空间 token、自有基础样式及起步页供用户在自己的项目中使用和修改；这不改变任何第三方代码的许可。未包含字体文件、原作 Logo、人物素材或商业图库资源。

`assets/motion-map.json` 的文件 blob SHA 来自 V9 的登记，保留为溯源线索；本次打包没有再次逐字核验十五个上游版本。main URL 是可变的，不等同锁定版本。可重复查看的实际代码由 `manifest.json` 锁定的参考 HTML 提供。
