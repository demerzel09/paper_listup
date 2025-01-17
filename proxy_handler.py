import time
import random
import logging
from typing import List, Dict, Optional

import requests
from scholarly import scholarly, ProxyGenerator
#from scholarly._proxy_generator import ProxyGenerator


def load_raw_proxies_from_csv(csv_file: str) -> List[str]:
    """
    CSV（1行1プロキシ）の内容をすべて読み込み、
    "ip:port" 形式の文字列リストを返す。
    """
    proxies = []
    with open(csv_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                proxies.append(line)
    return proxies


class MultiProxyScholarly:
    """
    - 大量の論文の参照数を取得したい場合を想定
    - コンストラクタで「HTTPS 接続が有効なプロキシ」をチェックし、max_proxies 個見つかり次第終了
    - 以降、プール内の複数プロキシ(各々 ProxyGenerator を保持)を切り替えて scholarly を利用
    - "Cannot fetch from Google Scholar." は except Exception で捕捉し、該当プロキシを除外
    - interval 管理で一定秒数以内の連続アクセスを回避
    """

    def __init__(
        self,
        all_proxy_urls: List[str],
        max_proxies: int = 5,
        min_interval: float = 5.0,
        max_interval: float = 15.0,
        # HTTPS の URL のみでテスト
        test_url: str = "https://httpbin.org/ip"
    ):
        """
        コンストラクタ。

        Parameters
        ----------
        all_proxy_urls : List[str]
            "ip:port" の文字列一覧（CSVなどから取得）
        max_proxies : int
            有効だと判定できたプロキシを何件ピックアップするか
        min_interval : float
            各プロキシのアクセス間隔の最小値(秒)
        max_interval : float
            各プロキシのアクセス間隔の最大値(秒)
        test_url : str
            HTTPSでのプロキシの有効性をテストするURL
            (ここでは "https://httpbin.org/ip" を利用)
        """
        self.logger = logging.getLogger("MultiProxyScholarly")
        self.logger.setLevel(logging.INFO)

        # プロキシをテストして、有効なものを最大 max_proxies だけ取得
        valid_proxies = self._validate_proxies(
            all_proxy_urls=all_proxy_urls,
            max_proxies=max_proxies,
            test_url=test_url,
            min_interval=min_interval,
            max_interval=max_interval
        )

        self.proxy_pool = valid_proxies  # ここでは既に上限まで取ったもの

        self.logger.info(
            f"Constructed MultiProxyScholarly with {len(self.proxy_pool)} valid HTTPS proxies "
            f"(out of {len(all_proxy_urls)})."
        )
        if not self.proxy_pool:
            self.logger.warning("No valid HTTPS proxies available at initialization.")

    def _validate_proxies(
        self,
        all_proxy_urls: List[str],
        max_proxies: int,
        test_url: str,
        min_interval: float,
        max_interval: float
    ) -> List[Dict]:
        """
        入力された proxy_urls をランダムにテストして、
        HTTPS 接続が OK なものを最大 max_proxies 個まで返す。

        Returns
        -------
        List[Dict]
          [{"proxy_url": ..., "pg": ..., "interval": float, "last_access": 0.0}, ...]
        """
        self.logger.info(
            f"Validating proxies over HTTPS... (max_proxies={max_proxies}, test_url={test_url})"
        )
        # proxy_urls をシャッフル
        random.shuffle(all_proxy_urls)

        valid_list = []
        for p_url in all_proxy_urls:
            if len(valid_list) >= max_proxies:
                break

            pg = ProxyGenerator()
            # scholarly 側では http/https 両方を設定しておくが、実質HTTPSが重要
            success = pg.SingleProxy(http=p_url, https=p_url)
            if not success:
                # 失敗したらスキップ
                continue

            # HTTPS 接続確認
            proxies_dict = {
                # HTTPではなくHTTPSでアクセスできるかどうかを確認
                "https": f"https://{p_url}"
            }
            try:
                # HTTPS で test_url へアクセスして 200 が返れば OK
                r = requests.get(test_url, proxies=proxies_dict, timeout=5)
                if r.status_code == 200:
                    interval = random.uniform(min_interval, max_interval)
                    valid_list.append({
                        "proxy_url": p_url,
                        "pg": pg,
                        "interval": interval,
                        "last_access": 0.0
                    })
                    self.logger.debug(f"[{p_url}] is valid HTTPS proxy (interval={interval:.2f}).")
                else:
                    self.logger.warning(f"[{p_url}] responded with code {r.status_code}, ignoring.")
            except Exception as e:
                self.logger.warning(f"[{p_url}] test request failed: {e}")

        self.logger.info(
            f"{len(valid_list)} HTTPS proxies are valid (out of {len(all_proxy_urls)}) up to max_proxies."
        )
        return valid_list

    def _get_available_pool(self) -> List[Dict]:
        """
        現在時刻で使用可能なプロキシ(pg)のリストを返す。
        last_access から interval 秒経過していれば使用可。
        """
        now = time.time()
        return [
            item for item in self.proxy_pool
            if (now - item["last_access"]) >= item["interval"]
        ]

    def _wait_for_any_proxy(self) -> None:
        """
        すべてのプロキシが使用不可の場合に、最も早く空くプロキシが
        利用可能になるまで sleep。
        """
        now = time.time()
        if not self.proxy_pool:
            self.logger.warning("No proxies left in pool to wait for.")
            return
        wait_times = [
            (item["interval"] - (now - item["last_access"]))
            for item in self.proxy_pool
        ]
        min_wait = max(min(wait_times), 0.1)
        self.logger.info(f"All proxies are busy. Waiting {min_wait:.1f} seconds...")
        time.sleep(min_wait)

    def _remove_proxy(self, item: Dict) -> None:
        """
        self.proxy_pool から該当要素を除外。
        """
        try:
            self.proxy_pool.remove(item)
            self.logger.info(f"Removed proxy {item['proxy_url']} from pool. {len(self.proxy_pool)} left.")
        except ValueError:
            pass

    def _pick_proxy_generator(self, max_pick_retry: int = 10) -> Optional[Dict]:
        """
        使用可能なプロキシをランダムに選び、そのpgを返す。
        max_pick_retry 回リトライしても駄目なら None。
        """
        for _ in range(max_pick_retry):
            if not self.proxy_pool:
                self.logger.warning("No proxy left in pool.")
                return None

            available = self._get_available_pool()
            if not available:
                self._wait_for_any_proxy()
                continue

            choice_item = random.choice(available)
            # ここでは既に pg が生成済みなので、再度 SingleProxy(...) は不要
            scholarly.use_proxy(choice_item["pg"])
            return choice_item

        return None

    def _mark_access_time(self, item: Dict) -> None:
        """
        指定のプール要素に対して、アクセス時刻を更新
        """
        item["last_access"] = time.time()

    def get_citation_count(self, paper_title: str, max_retry: int = 3) -> int:
        """
        タイトルで論文を検索し、先頭の論文の被引用数を返す。
        "Cannot fetch from Google Scholar." は except Exception で捕捉し、該当プロキシを除外。
        """
        for attempt in range(1, max_retry+1):
            if not self.proxy_pool:
                self.logger.error("No proxies are available, cannot continue.")
                return -4

            item = self._pick_proxy_generator()
            if item is None:
                self.logger.error("Failed to pick any HTTPS proxy generator.")
                return -3

            try:
                # 検索用イテレータ作成
                it = scholarly.search_pubs(paper_title)
                failed_url = getattr(it, "_url", "Unknown URL")

                first_pub = next(it, None)
                if first_pub is None:
                    self.logger.info(f"No publications found for '{paper_title}'.")
                    return -2

                filled_pub = scholarly.fill(first_pub)
                cites = filled_pub.get("num_citations", 0)

                self._mark_access_time(item)
                self.logger.info(f"[Attempt {attempt}] '{paper_title}' => {cites} citations.")
                return cites

            except Exception as e:
                # "Cannot fetch from Google Scholar." もここで捕捉
                if "Cannot fetch from Google Scholar." in str(e):
                    self.logger.warning(
                        f"[Attempt {attempt}] Cannot fetch from Google Scholar with {item['proxy_url']} "
                        f"(URL: {failed_url}) => removing this proxy."
                    )
                    self._remove_proxy(item)
                else:
                    self.logger.warning(
                        f"[Attempt {attempt}] Exception: {e} (URL: {failed_url}) => removing {item['proxy_url']}."
                    )
                    self._remove_proxy(item)

        self.logger.error(f"Failed to get citation count for '{paper_title}' after {max_retry} attempts.")
        return -1


if __name__ == "__main__":
    # 例: CSVファイルからすべてのプロキシURLを読み込む
    csv_filename = "free_proxy_list_2025_01_17.csv"
    all_proxy_urls = load_raw_proxies_from_csv(csv_filename)

    # MultiProxyScholarly を初期化
    # https://httpbin.org/ip を使ってHTTPS接続を確認するようにする
    mps = MultiProxyScholarly(
        all_proxy_urls=all_proxy_urls,
        max_proxies=5,
        min_interval=5.0,
        max_interval=15.0,
        test_url="https://httpbin.org/ip"   # HTTPS のURL
    )

    # いくつかのタイトルをテスト
    titles_to_check = [
        "Deep residual learning for image recognition",
        "Attention is all you need",
        "Adam: A method for stochastic optimization",
    ]
    for title in titles_to_check:
        cites = mps.get_citation_count(title, max_retry=3)
        print(f"Title: {title}")
        print(f"Citation Count: {cites}")
        print("-" * 40)
