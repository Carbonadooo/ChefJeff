"""Portable native/engine checks. The full upstream suite also has Linux/service tests."""
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
MODULES = [
    'test_native_desktop', 'test_native_timing', 'test_native_speed', 'test_native_bc', 'test_native_art', 'test_kitchen', 'test_spatial', 'test_service_mode',
    'test_map_definition', 'test_navigation_cache', 'test_shared_work',
    'test_split_kitchen', 'test_fire_spread', 'test_throw', 'test_throw_diagonals',
    'test_ground_assembly', 'test_direct_assembly', 'test_tableware',
    'test_heat_resume', 'test_route_stall', 'test_pot_swap', 'test_scoop',
    'test_vessels', 'test_ground_interaction', 'test_item_reach', 'test_handling',
    'test_surfaces', 'test_station_kinds', 'test_sink_unit', 'test_drying_rack',
    'test_repeat_delivery', 'test_stars', 'test_cabinet_front', 'test_corner_slide',
    'test_gentle_collision', 'test_navigation_cache', 'test_serving_footprint',
    'test_operation_docking', 'test_approach_partner', 'test_throw_scatter',
    'test_selection_parity', 'test_environment', 'test_data_driven',
]

if __name__ == '__main__':
    # No test journal belongs in the repository logs folder.
    os.environ.setdefault('CHEFJEFF_LOG_DIR', str(Path(tempfile.gettempdir()) / 'chefjeff-native-tests'))
    suite = unittest.defaultTestLoader.loadTestsFromNames(list(dict.fromkeys(MODULES)))
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    raise SystemExit(not result.wasSuccessful())
