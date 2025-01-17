import csv
import random
import requests
import logging

from typing import List
from scholarly import scholarly
from scholarly._proxy_generator import ProxyGenerator


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ProxyFilter")

# 例: この配列内の文字列を含むプロキシURLはすべて怪しいとみなし、スキップ
SUSPICIOUS_PATTERNS = [
    "httpbin.org",
    # "some-other-suspicious-domain.org",
    # "127.0.0.1",  # ローカルホストなど
    # ... 必要に応じて追加 ...
]


def load_proxies_from_csv(csv_file: str) -> List[str]:
    """
    CSV(1行1プロキシ)を読み込み、"ip:port"の文字列リストを返す
    """
    proxies = []
    with open(csv_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                proxies.append(line)
    return proxies


def is_blacklisted(proxy_url: str) -> bool:
    """
    ブラックリストパターンに該当すれば True を返す。
    """
    for suspicious in SUSPICIOUS_PATTERNS:
        if suspicious in proxy_url:
            return True
    return False


def is_scholarly_proxy_valid(proxy_url: str, verify_certificate: bool = True) -> bool:
    """
    指定の proxy_url ("ip:port") が以下の条件を満たすかを確認:
      1) ブラックリストに該当しない
      2) HTTPS で httpbin.org/ip 等にアクセスが成功する (200 OK) 
         + 証明書が正しく検証できる(verify_certificate=Trueなら)
      3) scholarly で SingleProxy(...) セット後、search_pubs がエラー("Cannot fetch...")にならない

    ここでは簡易的に "test" 検索を1回だけ実行。
    """
    # (0) まずブラックリストを確認
    if is_blacklisted(proxy_url):
        logger.debug(f"Proxy {proxy_url} is blacklisted by pattern.")
        return False

    logger.debug(f"Testing proxy: {proxy_url}")
    # (1) HTTPS 接続テスト (httpbin.org/ip で確認)
    proxies_dict = {
        "https": f"https://{proxy_url}",
        "http": f"http://{proxy_url}",  # scholarly 内部で http を参照する可能性がある
    }

    try:
        r = requests.get(
            "https://httpbin.org/ip",
            proxies=proxies_dict,
            timeout=5,
            verify=verify_certificate
        )
        if r.status_code != 200:
            logger.debug(f"HTTPS test failed. status={r.status_code}")
            return False
    except Exception as e:
        logger.debug(f"HTTPS test request failed for {proxy_url}: {e}")
        return False

    # (2) scholarly 用に ProxyGenerator を設定して試す
    pg = ProxyGenerator()
    success = pg.SingleProxy(http=proxy_url, https=proxy_url)
    if not success:
        logger.debug(f"SingleProxy setup failed for {proxy_url}")
        return False

    scholarly.use_proxy(pg)

    try:
        test_query = scholarly.search_pubs("test")
        # 実際に検索して1件だけ取得を試す
        next(test_query, None)
    except Exception as e:
        if "Cannot fetch from Google Scholar." in str(e):
            logger.debug(f"Cannot fetch from Google Scholar with {proxy_url}")
            return False
        logger.debug(f"Error while searching with {proxy_url}: {e}")
        return False

    logger.debug(f"Proxy {proxy_url} is valid for scholarly.")
    return True


def filter_proxies_and_save(
    input_csv: str,
    output_csv: str,
    verify_certificate: bool = True
):
    """
    input_csv から読み込んだプロキシを1つずつ検証し、
    - ブラックリストに該当するか？
    - HTTPS で通るか？
    - scholarly検索が通るか？
    OKなプロキシだけを output_csv に書き出す。

    verify_certificate=True の場合は SSL証明書を厳密検証。
    False にすれば自己署名などでも通ることがある。
    """
    logger.info(f"Loading proxies from {input_csv} ...")
    proxies_list = load_proxies_from_csv(input_csv)
    logger.info(f"{len(proxies_list)} proxies loaded. Checking them...")

    # 順序をランダム化
    random.shuffle(proxies_list)

    valid_proxies = []
    for p_url in proxies_list:
        if is_scholarly_proxy_valid(p_url, verify_certificate=verify_certificate):
            valid_proxies.append(p_url)

    logger.info(f"Found {len(valid_proxies)} valid proxies out of {len(proxies_list)} total.")

    # CSV に書き出し
    if valid_proxies:
        with open(output_csv, "w", encoding="utf-8", newline='') as f:
            writer = csv.writer(f)
            for vp in valid_proxies:
                writer.writerow([vp])
        logger.info(f"Saved valid proxies to {output_csv}.")
    else:
        logger.warning("No valid proxies found; no output CSV created.")


if __name__ == "__main__":
    # === 使い方 ===
    input_csv_file = "free_proxy_list_2025_01_17.csv"          # 入力: 既存のプロキシリスト(1行1プロキシ)
    output_csv_file = "filtered_proxies.csv"    # 出力: 厳選後のプロキシリスト

    # 証明書検証を有効にするとフリーのHTTPSプロキシは失格になりやすい
    # 必要に応じてFalseにして試す
    verify_certificate = True

    filter_proxies_and_save(
        input_csv=input_csv_file,
        output_csv=output_csv_file,
        verify_certificate=verify_certificate
    )
