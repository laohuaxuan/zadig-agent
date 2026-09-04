-- 平台用户与审计（参考 mse-domain-binding/deploy/sql/auth.sql）
USE `zadig_agent`;

CREATE TABLE IF NOT EXISTS `platform_users` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `name` VARCHAR(100) NOT NULL,
  `display_name` VARCHAR(120) NOT NULL DEFAULT '',
  `phone` VARCHAR(30) NULL,
  `email` VARCHAR(120) NOT NULL DEFAULT '',
  `password_hash` VARCHAR(255) NOT NULL DEFAULT '',
  `auth_source` VARCHAR(20) NOT NULL DEFAULT 'local',
  `feishu_open_id` VARCHAR(64) NULL,
  `role` VARCHAR(20) NOT NULL DEFAULT 'watcher',
  `status` VARCHAR(20) NOT NULL DEFAULT 'active',
  `created_at` DATETIME NOT NULL,
  `updated_at` DATETIME NOT NULL,
  `deleted_at` DATETIME NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_platform_users_name` (`name`),
  UNIQUE KEY `uk_platform_users_email` (`email`),
  UNIQUE KEY `uk_platform_users_feishu` (`feishu_open_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `audit_logs` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `user_id` BIGINT NULL,
  `username` VARCHAR(100) NOT NULL DEFAULT '',
  `display_name` VARCHAR(120) NOT NULL DEFAULT '',
  `action` VARCHAR(60) NOT NULL,
  `result` VARCHAR(20) NOT NULL DEFAULT '',
  `ip` VARCHAR(64) NOT NULL DEFAULT '',
  `detail` VARCHAR(1000) NOT NULL DEFAULT '',
  `created_at` DATETIME NOT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_audit_action` (`action`),
  KEY `idx_audit_user` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
