#!/bin/sh

set -eu

COMPOSE="${COMPOSE:-docker compose}"
SERVICES="${FULL_SERVICES:-postgres redis app}"
TIMEOUT="${FULL_TIMEOUT:-180}"
INTERVAL="${FULL_INTERVAL:-2}"
LOG_TAIL="${FULL_LOG_TAIL:-120}"

service_container_id() {
	service="$1"
	$COMPOSE ps -q "$service"
}

service_status() {
	service="$1"
	container_id="$(service_container_id "$service")"
	if [ -z "$container_id" ]; then
		printf '%s' "missing"
		return
	fi

	docker inspect \
		--format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' \
		"$container_id" 2>/dev/null || printf '%s' "missing"
}

print_ps() {
	printf '\n%s\n' "docker compose ps"
	$COMPOSE ps || true
}

print_logs() {
	service="$1"
	printf '\n%s\n' "--- logs: $service ---"
	$COMPOSE logs --tail="$LOG_TAIL" "$service" || true
}

print_diagnostics() {
	reason="$1"
	printf '\n%s\n' "Stack startup failed: $reason"
	print_ps
	print_logs app
	for service in $SERVICES; do
		if [ "$service" = "app" ]; then
			continue
		fi
		print_logs "$service"
	done
}

printf '%s\n' "Building and starting Docker Compose stack..."
if ! $COMPOSE up --build -d; then
	print_diagnostics "docker compose up --build -d exited with an error"
	exit 1
fi

printf '%s\n' "Waiting up to ${TIMEOUT}s for healthy services: $SERVICES"

deadline="$(( $(date +%s) + TIMEOUT ))"
last_snapshot=""

while :; do
	all_healthy=1
	current_snapshot=""

	for service in $SERVICES; do
		status="$(service_status "$service")"
		current_snapshot="${current_snapshot}${service}=${status} "

		case "$status" in
			healthy)
				;;
			created|running|restarting|starting|missing)
				all_healthy=0
				;;
			exited|dead|unhealthy)
				print_diagnostics "service '$service' is $status"
				exit 1
				;;
			*)
				all_healthy=0
				;;
		esac
	done

	current_snapshot="${current_snapshot% }"
	if [ "$current_snapshot" != "$last_snapshot" ]; then
		printf '%s\n' "Health: $current_snapshot"
		last_snapshot="$current_snapshot"
	fi

	if [ "$all_healthy" -eq 1 ]; then
		printf '\n%s\n' "Stack is healthy."
		printf '%s\n' "Services up: $SERVICES"
		printf '%s\n' "Migrations are applied by the app startup flow during container start."
		exit 0
	fi

	if [ "$(date +%s)" -ge "$deadline" ]; then
		print_diagnostics "timeout after ${TIMEOUT}s; last known health: $current_snapshot"
		exit 1
	fi

	sleep "$INTERVAL"
done
