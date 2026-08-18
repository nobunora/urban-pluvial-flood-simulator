#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>
#include <omp.h>

namespace {
void read_binary(const std::string& path, void* buffer, size_t item_size, size_t count) {
    FILE* f = std::fopen(path.c_str(), "rb");
    if (!f) { std::perror(path.c_str()); std::exit(2); }
    if (std::fread(buffer, item_size, count, f) != count) {
        std::fprintf(stderr, "short read: %s\n", path.c_str());
        std::exit(3);
    }
    std::fclose(f);
}

void write_binary(const std::string& path, const void* buffer, size_t item_size, size_t count) {
    FILE* f = std::fopen(path.c_str(), "wb");
    if (!f) { std::perror(path.c_str()); std::exit(4); }
    std::fwrite(buffer, item_size, count, f);
    std::fclose(f);
}
}

int main(int argc, char** argv) {
    // Usage:
    //   ./solver N dx duration_s rain_mm_h input_dir output_prefix
    if (argc < 7) {
        std::fprintf(stderr,
            "usage: %s N dx_m duration_s rain_mm_h input_dir output_prefix\n", argv[0]);
        return 1;
    }

    const int N = std::atoi(argv[1]);
    const float dx = std::atof(argv[2]);
    const double duration = std::atof(argv[3]);
    const float rain_mm_h = std::atof(argv[4]);
    const std::string input_dir = argv[5];
    const std::string prefix = argv[6];

    const long long NC = 1LL * N * N;
    const long long NX = 1LL * N * (N - 1); // x faces
    const long long NY = 1LL * (N - 1) * N; // y faces

    // Numerical parameters used in the reference run.
    const float g = 9.81f;
    const float cfl_alpha = 0.70f;
    const float theta = 0.80f;       // de Almeida-style q weighting
    const float hmin = 1e-5f;        // wet/dry threshold [m]
    const float dt_max = 2.0f;       // upper timestep cap [s]
    const float dt_min = 0.02f;      // safeguard only; check sensitivity if reached
    const float rain = (rain_mm_h / 1000.0f) / 3600.0f; // [m/s]

    std::vector<float> z(NC), h(NC, 0.f), hmax(NC, 0.f);
    std::vector<float> manning(NC), rain_weight(NC), donor_scale(NC, 1.f);
    std::vector<unsigned char> building(NC);
    std::vector<float> qx(NX, 0.f), qx_new(NX, 0.f);
    std::vector<float> qy(NY, 0.f), qy_new(NY, 0.f);

    read_binary(input_dir + "/z.bin", z.data(), sizeof(float), NC);
    read_binary(input_dir + "/manning.bin", manning.data(), sizeof(float), NC);
    read_binary(input_dir + "/rain_weight.bin", rain_weight.data(), sizeof(float), NC);
    read_binary(input_dir + "/building.bin", building.data(), sizeof(unsigned char), NC);

    double t = 0.0;
    long long step = 0;
    double next_log = 60.0;
    const auto wall0 = std::chrono::steady_clock::now();

    while (t < duration - 1e-12) {
        // Adaptive global CFL based on gravity-wave celerity sqrt(g h).
        float h_global_max = 0.f;
        #pragma omp parallel for reduction(max:h_global_max) schedule(static)
        for (long long a = 0; a < NC; ++a) {
            if (!building[a] && h[a] > h_global_max) h_global_max = h[a];
        }

        float dt = dt_max;
        if (h_global_max > hmin) {
            dt = cfl_alpha * dx / std::sqrt(g * h_global_max);
            dt = std::min(dt, dt_max);
            dt = std::max(dt, dt_min);
        }
        if (t + dt > duration) dt = static_cast<float>(duration - t);

        const float neighbour_weight = 0.5f * (1.f - theta);

        // ------------------------------------------------------------------
        // x-face Local-Inertial momentum update; positive qx points east.
        // ------------------------------------------------------------------
        #pragma omp parallel for schedule(static)
        for (int i = 0; i < N; ++i) {
            const long long cell_row = 1LL * i * N;
            const long long face_row = 1LL * i * (N - 1);
            for (int j = 0; j < N - 1; ++j) {
                const long long a = cell_row + j;
                const long long b = a + 1;
                const long long e = face_row + j;

                if (building[a] || building[b]) {
                    qx_new[e] = 0.f;
                    continue;
                }

                const float eta_a = z[a] + h[a];
                const float eta_b = z[b] + h[b];

                // Face water depth above the higher bed elevation.
                const float hf = std::max(eta_a, eta_b) - std::max(z[a], z[b]);
                if (hf <= hmin) {
                    qx_new[e] = 0.f;
                    continue;
                }

                const float q_left  = (j > 0)     ? qx[e - 1] : 0.f;
                const float q_right = (j < N - 2) ? qx[e + 1] : 0.f;
                const float qbar = theta * qx[e] + neighbour_weight * (q_left + q_right);

                const float slope = (eta_b - eta_a) / dx;
                const float nf = 0.5f * (manning[a] + manning[b]);
                const float h73 = hf * hf * std::cbrt(hf); // h^(7/3)

                // Semi-implicit Manning friction in the denominator.
                const float denominator =
                    1.f + g * dt * nf * nf * std::fabs(qbar) / std::max(h73, 1e-12f);

                float qn = (qbar - g * hf * dt * slope) / denominator;

                // Wet/dry direction guard.
                if (qn > 0.f && h[a] <= hmin && eta_a <= z[b] + hmin) qn = 0.f;
                if (qn < 0.f && h[b] <= hmin && eta_b <= z[a] + hmin) qn = 0.f;

                qx_new[e] = qn;
            }
        }

        // ------------------------------------------------------------------
        // y-face update; positive qy points north (increasing row index).
        // ------------------------------------------------------------------
        #pragma omp parallel for schedule(static)
        for (int i = 0; i < N - 1; ++i) {
            const long long face_row = 1LL * i * N;
            const long long cell_row = 1LL * i * N;
            for (int j = 0; j < N; ++j) {
                const long long a = cell_row + j;
                const long long b = a + N;
                const long long e = face_row + j;

                if (building[a] || building[b]) {
                    qy_new[e] = 0.f;
                    continue;
                }

                const float eta_a = z[a] + h[a];
                const float eta_b = z[b] + h[b];
                const float hf = std::max(eta_a, eta_b) - std::max(z[a], z[b]);
                if (hf <= hmin) {
                    qy_new[e] = 0.f;
                    continue;
                }

                const float q_down = (i > 0)     ? qy[e - N] : 0.f;
                const float q_up   = (i < N - 2) ? qy[e + N] : 0.f;
                const float qbar = theta * qy[e] + neighbour_weight * (q_down + q_up);

                const float slope = (eta_b - eta_a) / dx;
                const float nf = 0.5f * (manning[a] + manning[b]);
                const float h73 = hf * hf * std::cbrt(hf);
                const float denominator =
                    1.f + g * dt * nf * nf * std::fabs(qbar) / std::max(h73, 1e-12f);

                float qn = (qbar - g * hf * dt * slope) / denominator;
                if (qn > 0.f && h[a] <= hmin && eta_a <= z[b] + hmin) qn = 0.f;
                if (qn < 0.f && h[b] <= hmin && eta_b <= z[a] + hmin) qn = 0.f;
                qy_new[e] = qn;
            }
        }

        // ------------------------------------------------------------------
        // Positivity-preserving donor limiter.
        // A cell cannot export more water in dt than it currently contains
        // plus the rainfall source entering during the same timestep.
        // ------------------------------------------------------------------
        #pragma omp parallel for schedule(static)
        for (int i = 0; i < N; ++i) {
            for (int j = 0; j < N; ++j) {
                const long long a = 1LL * i * N + j;
                if (building[a]) {
                    donor_scale[a] = 1.f;
                    continue;
                }

                float outflow = 0.f;
                float q;
                if (j < N - 1) { q = qx_new[1LL * i * (N - 1) + j];     if (q > 0.f) outflow += q; }
                if (j > 0)     { q = qx_new[1LL * i * (N - 1) + j - 1]; if (q < 0.f) outflow -= q; }
                if (i < N - 1) { q = qy_new[1LL * i * N + j];           if (q > 0.f) outflow += q; }
                if (i > 0)     { q = qy_new[1LL * (i - 1) * N + j];     if (q < 0.f) outflow -= q; }

                const float available_depth = h[a] + rain * rain_weight[a] * dt;
                const float requested_depth = outflow * dt / dx;
                donor_scale[a] =
                    (requested_depth > available_depth && requested_depth > 0.f)
                    ? std::max(0.f, available_depth / requested_depth)
                    : 1.f;
            }
        }

        #pragma omp parallel for schedule(static)
        for (int i = 0; i < N; ++i) {
            const long long cell_row = 1LL * i * N;
            const long long face_row = 1LL * i * (N - 1);
            for (int j = 0; j < N - 1; ++j) {
                const long long a = cell_row + j;
                const long long b = a + 1;
                const long long e = face_row + j;
                const float q = qx_new[e];
                qx_new[e] = q * (q >= 0.f ? donor_scale[a] : donor_scale[b]);
            }
        }

        #pragma omp parallel for schedule(static)
        for (int i = 0; i < N - 1; ++i) {
            for (int j = 0; j < N; ++j) {
                const long long a = 1LL * i * N + j;
                const long long b = a + N;
                const long long e = 1LL * i * N + j;
                const float q = qy_new[e];
                qy_new[e] = q * (q >= 0.f ? donor_scale[a] : donor_scale[b]);
            }
        }

        // ------------------------------------------------------------------
        // Continuity equation + Rain-on-Grid.
        // Outer one-cell ring is treated as an open sink boundary.
        // ------------------------------------------------------------------
        #pragma omp parallel for schedule(static)
        for (int i = 0; i < N; ++i) {
            for (int j = 0; j < N; ++j) {
                const long long a = 1LL * i * N + j;

                if (building[a]) {
                    h[a] = 0.f;
                    hmax[a] = 0.f;
                    continue;
                }

                float dhdt = rain * rain_weight[a];
                if (j < N - 1) dhdt -= qx_new[1LL * i * (N - 1) + j] / dx;
                if (j > 0)     dhdt += qx_new[1LL * i * (N - 1) + j - 1] / dx;
                if (i < N - 1) dhdt -= qy_new[1LL * i * N + j] / dx;
                if (i > 0)     dhdt += qy_new[1LL * (i - 1) * N + j] / dx;

                float hn = h[a] + dt * dhdt;
                if (hn < 0.f) hn = 0.f; // limiter should make this only roundoff-scale

                if (i == 0 || j == 0 || i == N - 1 || j == N - 1) hn = 0.f;

                h[a] = hn;
                if (hn > hmax[a]) hmax[a] = hn;
            }
        }

        qx.swap(qx_new);
        qy.swap(qy_new);
        t += dt;
        ++step;

        if (t >= next_log || t >= duration - 1e-8) {
            float hm = 0.f;
            #pragma omp parallel for reduction(max:hm) schedule(static)
            for (long long a = 0; a < NC; ++a) hm = std::max(hm, h[a]);
            const double wall = std::chrono::duration<double>(
                std::chrono::steady_clock::now() - wall0).count();
            std::fprintf(stderr,
                "t=%.1f s step=%lld dt=%.4f s hmax=%.4f m wall=%.1f s\n",
                t, step, dt, hm, wall);
            next_log += 60.0;
        }
    }

    write_binary(prefix + "_h.bin", h.data(), sizeof(float), NC);
    write_binary(prefix + "_hmax.bin", hmax.data(), sizeof(float), NC);
    write_binary(prefix + "_qx.bin", qx.data(), sizeof(float), NX);
    write_binary(prefix + "_qy.bin", qy.data(), sizeof(float), NY);

    std::fprintf(stderr, "DONE steps=%lld\n", step);
    return 0;
}
