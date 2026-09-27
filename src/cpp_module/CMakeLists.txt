cmake_minimum_required(VERSION 3.20)
project(document_enhancer LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_executable(document_enhancer enhancer.cpp)
target_compile_options(document_enhancer PRIVATE -O3)
