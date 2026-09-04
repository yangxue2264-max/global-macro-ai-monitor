from core.providers import _parse_sina_auction, _parse_tencent_auction


sina_fields = ["测试股份", "10.50", "10.00", "10.50", "10.50", "10.50", "10.49", "10.50", "100000", "1050000"]
sina_fields += [""] * 20 + ["2026-09-04", "09:25:00", "00"]
sina_text = f'var hq_str_sh600000="{",".join(sina_fields)}";'
sina = _parse_sina_auction(sina_text, {"sh600000": "600000.SS"})
assert sina["600000.SS"]["gap_pct"] == 5.0
assert sina["600000.SS"]["auction_price"] == 10.5

tencent_fields = [""] * 40
tencent_fields[1] = "测试股份"
tencent_fields[4] = "10.00"
tencent_fields[5] = "9.70"
tencent_fields[6] = "1000"
tencent_fields[30] = "20260904092500"
tencent_text = f'v_sh600000="{"~".join(tencent_fields)}";'
tencent = _parse_tencent_auction(tencent_text, {"sh600000": "600000.SS"})
assert tencent["600000.SS"]["gap_pct"] == -3.0
assert tencent["600000.SS"]["auction_price"] == 9.7

print("AUCTION_PROVIDER_TEST_OK")
