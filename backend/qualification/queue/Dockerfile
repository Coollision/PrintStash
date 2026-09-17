FROM rust:1.91.0-bookworm@sha256:e187887ec511b3d93e45c0231d2f0fd59f1347526c58aa86343aa83c74f3e1a9 AS build

WORKDIR /source
COPY Cargo.toml Cargo.lock ./
COPY src ./src
COPY tests ./tests
RUN cargo build --release --locked --bin queue-qualification

FROM debian:bookworm-slim@sha256:88200866dfff7ea7f5cbcb6ec7c8a701889efe6fe859fe64d6990e4b07ea4171

RUN useradd --create-home --uid 10001 qualification
COPY --from=build /source/target/release/queue-qualification /usr/local/bin/queue-qualification
USER qualification
ENTRYPOINT ["/usr/local/bin/queue-qualification"]
