FROM golang:1.23 AS builder
WORKDIR /build
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -o /token-service .

FROM registry.access.redhat.com/ubi9-minimal:latest
COPY --from=builder /token-service /usr/local/bin/token-service
EXPOSE 8081
ENTRYPOINT ["/usr/local/bin/token-service"]
