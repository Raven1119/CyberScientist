# V9 代码定位索引

基准文件：`assets/reference.html`；文件未改写。行号固定于包内 SHA-256。所有脚本均为经典脚本，不能当成独立 ES module 直接 import。

| Script | HTML 行号 | 内容 |
|---|---:|---|
| 1 | 69–71 | 第三方许可证（保留） |
| 2 | 72–462 | GLSL 常量及 shader helpers |
| 3 | 463–693 | Motion 主机：动效、WebGL、生命周期 |
| 4 | 694–880 | 演示业务、Target Cursor、Stepper |

## 15 个动效

| ID | 效果 | script / 行号 | 搜索锚点 |
|---|---|---|---|
| PS-06 | Dithering | 2 / 126 | `const DITHERING =` |
| PS-10 | Metaballs | 2 / 290 | `const PAPER_META =` |
| RB-01 | Threads | 2 / 341 | `const THREADS =` |
| RB-08 | Dot Grid | 3 / 670 | `function dotGrid(` |
| RB-16 | Particles | 2 / 425 | `const PARTICLE_VERTEX =` |
| RB-29 | Target Cursor | 4 / 815 | `function targetCursor(` |
| RB-34 | Pixel Transition | 3 / 490 | `function pixelTransition(` |
| RB-35 | Animated Content | 3 / 553 | `function enter(` |
| RB-44 | Meta Balls | 2 / 395 | `const RB_META =` |
| RB-45 | Decrypted Text | 3 / 523 | `function decrypt(` |
| RB-46 | Scrambled Text | 3 / 555 | `function scrambled(` |
| RB-48 | Split Text | 3 / 547 | `function split(` |
| RB-53 | Text Type | 3 / 539 | `function type(` |
| RB-59 | Elastic Slider | 3 / 568 | `function elastic(` |
| RB-60 | Stepper | 4 / 802 | `function stepTo(` |

来源链接、记录的文件 blob SHA、用途与方法签名见 `assets/motion-map.json`。这些 blob SHA 不能用作 Git commit SHA。上游 main 链接可能更新；本包的复现基准始终是本地 HTML。
