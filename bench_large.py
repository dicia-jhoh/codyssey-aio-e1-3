"""큰 N 에서 MAC 시간을 다시 재는 스크립트 — 평균만이 아니라 흔들림(표준편차)까지 낸다.

실행: python bench_large.py              → 25·100·250·500·1000, 각 10회
      python bench_large.py 1000 2000 -r 5 → 원하는 크기·반복 횟수

main.py 의 mac()·패턴 생성기를 그대로 쓴다. 표준 라이브러리만 쓴다.
"""

import argparse
import gc
import statistics
import sys
import time

import main

DEFAULT_SIZES = [25, 100, 250, 500, 1000]


def measure(n, repeat):
    """n×n 패턴으로 mac() 을 repeat 번 잰 각 회차 시간(ms) 목록.

    첫 1회는 버린다(워밍업) — 처음 부르는 순간엔 메모리 할당·캐시가 덜 데워져 혼자 느리다.
    잴 때는 가비지 컬렉터를 잠깐 끈다 — 측정 중간에 GC 가 끼면 그 회차만 튄다.
    """
    a = main.generate_cross(n)
    b = main.generate_x(n)
    main.mac(a, b)
    times = []
    gc.disable()
    try:
        for _ in range(repeat):
            start = time.perf_counter()
            main.mac(a, b)
            times.append((time.perf_counter() - start) * 1000)
    finally:
        gc.enable()
    return times


def main_cli(argv=None):
    parser = argparse.ArgumentParser(description="큰 N 의 MAC 시간·표준편차")
    parser.add_argument("sizes", nargs="*", type=int, default=DEFAULT_SIZES)
    parser.add_argument("-r", "--repeat", type=int, default=10)
    args = parser.parse_args(argv)

    print(f"Python {sys.version.split()[0]} · 반복 {args.repeat}회(워밍업 1회 제외)")
    print(f"{'크기':>10} {'연산 횟수':>12} {'평균(ms)':>10} {'표준편차':>9} {'최소':>9} {'최대':>9} {'흔들림':>7}")
    for n in args.sizes:
        times = measure(n, args.repeat)
        mean = statistics.mean(times)
        stdev = statistics.stdev(times) if len(times) > 1 else 0.0
        print(
            f"{n:>5}×{n:<4} {n * n:>12,} {mean:>10.3f} {stdev:>9.3f} "
            f"{min(times):>9.3f} {max(times):>9.3f} {stdev / mean * 100:>6.1f}%"
        )


if __name__ == "__main__":
    main_cli()
