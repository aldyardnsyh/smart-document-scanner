#include <algorithm>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>

int main(int argc, char* argv[]) {
    if (argc < 6 || argc > 7) {
        return 2;
    }
    try {
        const int block_size = std::stoi(argv[3]);
        const int width = std::stoi(argv[4]);
        const int height = std::stoi(argv[5]);
        const bool fast_denoise = argc == 7 && std::string(argv[6]) == "--fast-denoise";
        if (block_size < 3 || block_size % 2 == 0 || width <= 0 || height <= 0) {
            return 3;
        }
        const std::size_t pixel_count = static_cast<std::size_t>(width) * height;
        std::vector<std::uint8_t> source(pixel_count);
        std::ifstream input(argv[1], std::ios::binary);
        input.read(reinterpret_cast<char*>(source.data()), static_cast<std::streamsize>(pixel_count));
        if (!input || static_cast<std::size_t>(input.gcount()) != pixel_count) {
            return 4;
        }
        const int radius = fast_denoise ? 2 : 1;
        std::vector<std::uint8_t> denoised(pixel_count);
        for (int y = 0; y < height; ++y) {
            for (int x = 0; x < width; ++x) {
                int total = 0;
                int count = 0;
                for (int offset_y = -radius; offset_y <= radius; ++offset_y) {
                    for (int offset_x = -radius; offset_x <= radius; ++offset_x) {
                        const int sample_x = std::clamp(x + offset_x, 0, width - 1);
                        const int sample_y = std::clamp(y + offset_y, 0, height - 1);
                        total += source[static_cast<std::size_t>(sample_y) * width + sample_x];
                        ++count;
                    }
                }
                denoised[static_cast<std::size_t>(y) * width + x] =
                    static_cast<std::uint8_t>(total / count);
            }
        }
        const int stride = width + 1;
        std::vector<long long> integral(static_cast<std::size_t>(stride) * (height + 1), 0);
        for (int y = 1; y <= height; ++y) {
            long long row_sum = 0;
            for (int x = 1; x <= width; ++x) {
                row_sum += denoised[static_cast<std::size_t>(y - 1) * width + x - 1];
                integral[static_cast<std::size_t>(y) * stride + x] =
                    integral[static_cast<std::size_t>(y - 1) * stride + x] + row_sum;
            }
        }
        const int half = block_size / 2;
        std::vector<std::uint8_t> output(pixel_count);
        for (int y = 0; y < height; ++y) {
            const int y0 = std::max(0, y - half);
            const int y1 = std::min(height, y + half + 1);
            for (int x = 0; x < width; ++x) {
                const int x0 = std::max(0, x - half);
                const int x1 = std::min(width, x + half + 1);
                const long long total =
                    integral[static_cast<std::size_t>(y1) * stride + x1]
                    - integral[static_cast<std::size_t>(y0) * stride + x1]
                    - integral[static_cast<std::size_t>(y1) * stride + x0]
                    + integral[static_cast<std::size_t>(y0) * stride + x0];
                const double mean = static_cast<double>(total) / ((x1 - x0) * (y1 - y0));
                const double value = denoised[static_cast<std::size_t>(y) * width + x];
                const double contrasted = std::clamp(value + (value - mean) * 0.8, 0.0, 255.0);
                const double threshold = contrasted + 7.0 < mean ? 0.0 : 255.0;
                output[static_cast<std::size_t>(y) * width + x] =
                    static_cast<std::uint8_t>(std::round(contrasted * 0.68 + threshold * 0.32));
            }
        }
        std::ofstream output_file(argv[2], std::ios::binary);
        output_file.write(
            reinterpret_cast<const char*>(output.data()),
            static_cast<std::streamsize>(output.size())
        );
        return output_file ? 0 : 5;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 6;
    }
}
