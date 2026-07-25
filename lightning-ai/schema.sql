-- Lightning AI database schema
-- This runs automatically via SQLAlchemy (db.create_all()) too,
-- but you can run this manually if you prefer.

CREATE DATABASE IF NOT EXISTS lightning_ai
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE lightning_ai;

CREATE TABLE IF NOT EXISTS users (
  id INT AUTO_INCREMENT PRIMARY KEY,
  google_id VARCHAR(255) NOT NULL UNIQUE,
  email VARCHAR(255) NOT NULL UNIQUE,
  name VARCHAR(255),
  profile_pic VARCHAR(500),
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chat_history (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  message_type VARCHAR(20) DEFAULT 'chat',
  question TEXT,
  answer TEXT,
  image_path VARCHAR(500),
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
