# Pitfalls — ブラウザ自動化（スクリーンショット撮影・E2E）

ポータルの画面を撮る、E2E を回す、UI の挙動を確認する、といった目的で Playwright /
Chrome DevTools の MCP を使うときの罠。**ここに書いてあるものは実際に踏んで、対話を
数分ブロックした**。

## init script は蓄積し、解除できない

`page.addInitScript()` は**呼んだ回数だけ登録が積み上がり、以降のリロードで毎回すべてが
再実行される**。解除する API は無い。したがって「前に入れたスクリプトを直したいので
もう一度 addInitScript する」は、直した版が**追加**されるだけで、壊れた版は残り続ける。

| やらない | やる |
|---|---|
| `addInitScript` を試行錯誤で複数回呼ぶ | 撮影直前に `page.evaluate()` で 1 回だけ実行する |
| 壊れた init script を新しい init script で上書きしようとする | ページ（またはコンテキスト）を作り直す |
| リロードで前の状態が消えると期待する | init script はリロードで**再実行される**と考える |

置換や整形をページに適用したいだけなら、init script は要らない。`evaluate()` を
スクリーンショットの直前に呼べば十分で、しかも副作用が 1 回で終わる。

## 自分の書き換えを監視する MutationObserver を作らない

DOM を書き換える処理を `MutationObserver` のコールバックから呼ぶと、書き換えが次の
mutation を生み、それがまたコールバックを呼ぶ。実測で**レンダラーが CPU 107% で回り
続け**、`page.reload()` も `browser_tabs list` も返らなくなった。画面の描画自体は通るので
「見た目は正常なのに自動化だけ固まる」という分かりにくい形で出る。

`textContent` への代入は、**同じ値を入れても** childList の mutation を発生させる。
`nodeValue` も同様。「変わったときだけ代入する」ガードを書いたつもりでも、比較対象を
間違えると（例: `el.value || el.textContent` のように別プロパティを見てしまう）ループする。

安全な形:

```js
// 監視しない。撮る直前に 1 回呼ぶだけ。
const replaced = await page.evaluate((subs) => {
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const hits = [];
  while (walker.nextNode()) {
    const n = walker.currentNode;
    let v = n.nodeValue || "";
    let changed = false;
    for (const [from, to] of subs) {
      if (v.includes(from)) { v = v.split(from).join(to); changed = true; }
    }
    if (changed) hits.push([n, v]);   // 収集してから書く
  }
  for (const [n, v] of hits) n.nodeValue = v;
  return hits.length;                 // 0 なら置換対象が無い＝取りこぼしの検知に使える
}, SUBS);
```

戻り値を返させるのが重要。`0` は「置換対象が無かった」ことを意味し、SPA の再描画で
置換が巻き戻ったのか、そもそも対象が画面に無いのかを切り分けられる。

## 固まったときの切り分け手順

自動化が返らなくなったら、**リトライしない**。同じ呼び出しを重ねるとタイムアウト待ちが
積み上がるだけで、原因は消えない。

```bash
# 1. 暴走しているレンダラーを特定する
ps aux | grep -i 'Google Chrome' | grep -v grep | sort -k3 -rn | head -3 \
  | awk '{printf "pid=%s cpu=%s%%\n", $2, $3}'
# CPU が 100% 付近のプロセスが 1 つあれば、ページ内のループを疑う

# 2. そのレンダラーだけ停止する（タブが落ちるだけで、他のタブとプロファイルは残る）
kill <pid>

# 3. 正常化を確認する
ps aux | grep -i 'Google Chrome' | grep -v grep | sort -k3 -rn | head -3
```

レンダラーを落とすと、そのページに紐づいていた init script も一緒に消える。復旧後は
サインインし直しになる（このリポジトリでは Cognito のパスワードで再ログインできる）。

## ページ再作成によるビューポート指定の消失

`browser_resize` はページ単位。タブを落として開き直すと既定サイズに戻るので、撮影を
再開する前に**もう一度リサイズする**。これを忘れると、セット内に 1 枚だけ寸法の違う
画像が混ざる（実際に 1512x861 が 1 枚混ざった）。

撮影後に寸法を検証しておくと取りこぼさない:

```bash
python3 - <<'PY'
from PIL import Image
import pathlib
for p in sorted(pathlib.Path('docs/screenshots').glob('*.png')):
    if p.name.startswith(('phase', 'uc')): continue
    s = Image.open(p).size
    if s != (1512, 900):
        print(f"{p.name:44} {s}")
PY
```

## SPA における「クリックできない」の原因としての DOM 不安定性

Playwright はクリック前に要素が visible / enabled / stable になるのを待つ。ログに
`element is visible, enabled and stable` → `performing click action` まで出てから
タイムアウトする場合、要素の問題ではなく**ページが絶えず mutation を発生させていて
安定判定が通らない**ことを疑う。上のループがまさにこれだった。

## 撮影時の識別子マスクで踏襲する前例

このリポジトリのポータル画面は、黒塗りではなく**撮影前に DOM 上で値を差し替える**方式で
公開されている。コミット済みの画像に実際に使われている値:

| 実際の値の種類 | 公開画像での値 |
|---|---|
| ファイルシステム ID 由来のクラスタ名 | `FsxIdCluster` / `FsxIdPeerCluster` |
| ピアクラスタ名 | `cluster-osaka` / `cluster-singapore` |
| ピア SVM 名 | `svm_src` / `svm_dst` / `svm_onprem` |
| intercluster LIF / ピアのアドレス | RFC 5737 の `198.51.100.x` |
| 特定の 1 台を指すクライアント IP | RFC 5737 の `203.0.113.99` |
| AD ドメイン | `EXAMPLE.LOCAL` |

新しく撮るときは、まず**置き換える対象の既存画像を開いて何に置換されているかを確認する**。
先に撮ってから考えると、実 ID の入った画像をコミットしかける。置換表は
`docs/screenshots/originals/portal-refresh/_substitutions.json`（gitignore）に残してある。

検証は OCR を入れなくてもバイナリ grep で足りる:

```bash
LC_ALL=C grep -aoE '<実 ID>|<実 IP>|<実クラスタ名>' docs/screenshots/*.png
# 出力が無ければ、少なくともその文字列は画像に残っていない
```

## 不可逆操作のダイアログは「開くだけ」

Snapshot のロックのように取り消せない操作の確認ダイアログを撮るときは、開いて撮って
**キャンセルする**。確定ボタンは押さない。撮影のために不可逆操作を実行すると、その
リソースは保持期間が切れるまで削除できなくなる（`pitfalls-snaplock` を参照）。
