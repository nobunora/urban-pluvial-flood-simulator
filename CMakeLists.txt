cmake_minimum_required(VERSION 3.16)
project(local_inertial_flood_reference LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

find_package(OpenMP REQUIRED)

add_executable(local_inertial_solver src/solver.cpp)
target_link_libraries(local_inertial_solver PRIVATE OpenMP::OpenMP_CXX)

if(MSVC)
    target_compile_options(local_inertial_solver PRIVATE /O2)
else()
    target_compile_options(local_inertial_solver PRIVATE -O3 -march=native)
endif()
