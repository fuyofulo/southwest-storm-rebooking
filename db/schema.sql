-- Denver storm rebooking helper: Supabase (Postgres) schema.
-- Run once in the Supabase SQL editor (or psql), then `python -m scripts.seed`.
-- Times are local airport times with no time zone in the source data, so they are
-- stored as `timestamp` (without time zone).

create table if not exists bookings (
    booking_id                    text primary key,
    party_size                    integer not null check (party_size > 0),
    lead_passenger_name           text not null,
    cancelled_flight_no           text not null,
    origin_airport                text not null,
    destination_airport           text not null,
    scheduled_departure           timestamp not null,
    cancellation_time             timestamp not null,
    fare_class                    text not null check (fare_class in
                                    ('Wanna Get Away', 'Wanna Get Away Plus', 'Anytime', 'Business Select')),
    fare_paid_usd                 numeric(10, 2) not null check (fare_paid_usd >= 0),  -- whole party
    waiver_eligible               boolean not null,  -- read as given, never re-assessed (bulletin 1.3, 1.4)
    onward_connection_flight_no   text,
    has_checked_bags              boolean not null,
    needs_wheelchair_assist       boolean not null,
    travels_with_infant           boolean not null,
    loyalty_tier                  text not null,
    hotel_voucher_issued          boolean not null,
    earliest_acceptable_departure timestamp not null,
    agent_note                    text
);

-- One row per person. Derived by the seed script from party_size, travels_with_infant
-- and agent_note (the source data has no per-passenger field). `source` says how.
create table if not exists passengers (
    booking_id     text not null references bookings (booking_id) on delete cascade,
    seq            integer not null check (seq > 0),
    label          text not null,
    passenger_type text not null check (passenger_type in ('adult', 'child', 'lap_infant', 'unknown')),
    source         text not null,
    primary key (booking_id, seq)
);

create table if not exists flights (
    flight_no               text primary key,
    origin_airport          text not null,
    destination_airport     text not null,
    departure_datetime      timestamp not null,
    arrival_datetime        timestamp not null,
    aircraft_type           text not null,
    open_seats_total        integer not null check (open_seats_total >= 0),
    open_seats_adjacent_max integer not null check (open_seats_adjacent_max between 0 and open_seats_total),
    fare_class_open         text not null,
    base_fare_usd           numeric(10, 2) not null check (base_fare_usd >= 0),  -- per seat
    flight_status           text not null check (flight_status in ('scheduled', 'delayed', 'cancelled')),
    weather_risk_flag       boolean not null,
    check (arrival_datetime > departure_datetime)
);

create index if not exists flights_route_departure on flights (origin_airport, destination_airport, departure_datetime);

-- Tell Supabase's REST API to pick up the new tables right away (harmless elsewhere).
notify pgrst, 'reload schema';
