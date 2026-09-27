from floodsim.results.viewport_cache import GIB, cache_budget_from_memory


def test_cache_budget_keeps_system_headroom_and_can_stream_at_pressure() -> None:
    constrained = cache_budget_from_memory(available_bytes=2 * GIB, total_bytes=8 * GIB)
    assert constrained.safety_headroom_bytes == 2 * GIB
    assert constrained.budget_bytes == 0

    normal = cache_budget_from_memory(available_bytes=20 * GIB, total_bytes=32 * GIB)
    assert normal.safety_headroom_bytes == max(2 * GIB, (32 * GIB) // 5)
    assert normal.budget_bytes == min(4 * GIB, ((20 * GIB - normal.safety_headroom_bytes) * 35) // 100)
