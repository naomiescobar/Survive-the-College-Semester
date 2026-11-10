-- Survive the College Semester
-- CSC335-02 Fall 2026
-- Login Database Setup

CREATE DATABASE IF NOT EXISTS college_survival;
USE college_survival;

CREATE TABLE IF NOT EXISTS players (
    player_id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,

    -- Student survival stats
    energy INT NOT NULL DEFAULT 100,
    money DECIMAL(8,2) NOT NULL DEFAULT 500.00,
    stress INT NOT NULL DEFAULT 0,
    homework INT NOT NULL DEFAULT 0,
    attendance INT NOT NULL DEFAULT 100,

    -- College journey
    semester_week INT NOT NULL DEFAULT 1,

    -- Weekly game state
    -- actions_left: action points remaining this week (week ends at 0)
    -- event_chance: percent chance a random event happens after the next action
    actions_left INT NOT NULL DEFAULT 3,
    event_chance INT NOT NULL DEFAULT 15,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_energy
        CHECK (energy BETWEEN 0 AND 100),
    CONSTRAINT chk_stress
        CHECK (stress BETWEEN 0 AND 100),
    CONSTRAINT chk_homework
        CHECK (homework BETWEEN 0 AND 100),
    CONSTRAINT chk_attendance
        CHECK (attendance BETWEEN 0 AND 100),
    CONSTRAINT chk_week
        CHECK (semester_week BETWEEN 1 AND 16),
    CONSTRAINT chk_actions
        CHECK (actions_left >= 0),
    CONSTRAINT chk_event_chance
        CHECK (event_chance BETWEEN 0 AND 100)
);

-- Login lookup:
-- Your application must use a parameterized query.
SELECT player_id, username, password_hash
FROM players
WHERE username = ?;

-- Load the player's game stats after successful login.
SELECT player_id, username, energy, money, stress,
       homework, attendance, semester_week,
       actions_left, event_chance
FROM players
WHERE player_id = ?;