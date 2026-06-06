#!/bin/bash
set -e

E2SIM_DIR=/ocp-e2sim
BS_CONNECTOR="$E2SIM_DIR/e2sm_examples/kpm_e2sm/src/kpm/bs_connector.cpp"
KPM_BUILD="$E2SIM_DIR/e2sm_examples/kpm_e2sm/build"

cd "$E2SIM_DIR"

needs_build=0

if grep -q "timer expired for requestorId %ld, instanceId %ld, ranFunctionId %ld, actionId %ld: 500 ms" "$BS_CONNECTOR"; then
  sed -i \
    -e "s/timer expired for requestorId %ld, instanceId %ld, ranFunctionId %ld, actionId %ld: 500 ms/timer expired for requestorId %ld, instanceId %ld, ranFunctionId %ld, actionId %ld: %d s, forced to 500 ms/" \
    "$BS_CONNECTOR"
  needs_build=1
fi

if grep -q "std::chrono::seconds configured_sleep_duration(timer\[0\]);" "$BS_CONNECTOR"; then
  # Force the emulator report loop to the course-required 500 ms interval.
  sed -i \
    -e "s/std::chrono::seconds configured_sleep_duration(timer\[0\]);/std::chrono::milliseconds configured_sleep_duration(500);/" \
    -e "s/timer expired for requestorId %ld, instanceId %ld, ranFunctionId %ld, actionId %ld: %d s/timer expired for requestorId %ld, instanceId %ld, ranFunctionId %ld, actionId %ld: %d s, forced to 500 ms/" \
    "$BS_CONNECTOR"
  needs_build=1
fi

if [ "$needs_build" = "1" ]; then
  cmake --build "$KPM_BUILD" --target kpm_sim -j "$(nproc)"
fi

if [ "${PATCH_ONLY:-0}" = "1" ]; then
  exit 0
fi

chmod +x run_e2sim.sh
./run_e2sim.sh
