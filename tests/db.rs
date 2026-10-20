//! Integration tests for the SQLite layer, run against a throwaway in-memory
//! database. They exercise the public API the handlers rely on.

use anontrizun_bot::db::Database;

async fn database() -> Database {
    Database::connect_in_memory()
        .await
        .expect("in-memory database")
}

#[tokio::test]
async fn register_user_creates_an_eight_character_code() {
    let db = database().await;
    let stats = db.register_user(1, None).await.unwrap();

    assert_eq!(stats.anon_code.len(), 8);
    assert!(stats.anon_code.chars().all(|c| c.is_ascii_alphanumeric()));
    assert_eq!(stats.balance, 0);
    assert!(!stats.is_vip);
    assert!(stats.show_vip_cats);
    assert!(stats.show_achievements);
    assert_eq!(stats.code_auto_refresh, "never");
}

#[tokio::test]
async fn register_user_keeps_the_existing_code_and_state() {
    let db = database().await;
    let first = db.register_user(1, None).await.unwrap();
    db.give_balance(250, 1).await.unwrap();
    db.increment_sent_count(1).await.unwrap();

    let second = db.register_user(1, None).await.unwrap();

    assert_eq!(second.anon_code, first.anon_code);
    assert_eq!(second.balance, 250);
    assert_eq!(second.sent_count, 1);
    assert_eq!(db.get_all_user_ids().await.unwrap(), vec![1]);
}

#[tokio::test]
async fn register_user_tolerates_unknown_and_self_referrers() {
    let db = database().await;

    let referred = db.register_user(10, Some(999)).await.unwrap();
    assert_eq!(referred.anon_code.len(), 8);

    let self_referral = db.register_user(20, Some(20)).await.unwrap();
    let second = db.register_user(20, Some(10)).await.unwrap();

    assert_eq!(self_referral.anon_code, second.anon_code);
    assert_eq!(db.get_all_user_ids().await.unwrap().len(), 2);
}

#[tokio::test]
async fn unregistered_users_get_default_stats() {
    let db = database().await;
    let stats = db.get_user_stats(42).await.unwrap();

    assert_eq!(stats.anon_code, "НЕИЗВЕСТНО");
    assert_eq!(stats.code_auto_refresh, "never");
    assert_eq!(stats.balance, 0);
}

#[tokio::test]
async fn ban_and_unban_round_trip() {
    let db = database().await;
    db.register_user(1, None).await.unwrap();

    assert!(!db.is_banned(1));
    assert_eq!(
        db.get_banned_anon_code_by_user_id(1).await.unwrap(),
        "НЕИЗВЕСТНО"
    );

    db.ban_user(1, "ABCD1234").await.unwrap();
    assert!(db.is_banned(1));
    assert_eq!(
        db.get_banned_anon_code_by_user_id(1).await.unwrap(),
        "ABCD1234"
    );
    assert_eq!(
        db.get_banned_user_id_by_anon_code("ABCD1234")
            .await
            .unwrap(),
        Some(1)
    );

    let banned = db.get_banned_users().await.unwrap();
    assert_eq!(banned.len(), 1);
    assert_eq!(banned[0].user_id, 1);
    assert_eq!(banned[0].anon_code, "ABCD1234");

    let new_code = db.unban_user(1).await.unwrap();
    assert_eq!(new_code.len(), 8);
    assert!(!db.is_banned(1));
    assert!(db.get_banned_users().await.unwrap().is_empty());
}

#[tokio::test]
async fn regenerating_a_code_clears_the_old_references() {
    let db = database().await;
    let stats = db.register_user(1, None).await.unwrap();
    let old_code = stats.anon_code.clone();
    db.add_message(100, 1, &old_code, false, 7).await.unwrap();

    let (success, new_code) = db.regenerate_user_code(1).await.unwrap();

    assert!(success);
    assert_ne!(new_code, old_code);
    assert_eq!(db.get_user_stats(1).await.unwrap().anon_code, new_code);
    assert_eq!(
        db.get_admin_msg_id_by_user_msg_id(1, 7).await.unwrap(),
        Some(100)
    );

    // The stored code is dropped, so lookups fall back to the current one.
    let fallback = db
        .get_sender_with_code_by_admin_msg(100)
        .await
        .unwrap()
        .expect("fallback sender");
    assert_eq!(fallback.sender_id, 1);
    assert_eq!(fallback.anon_code, new_code);
}

#[tokio::test]
async fn banned_users_cannot_regenerate_their_code() {
    let db = database().await;
    db.register_user(1, None).await.unwrap();
    db.ban_user(1, "ABCD1234").await.unwrap();

    let (success, message) = db.regenerate_user_code(1).await.unwrap();

    assert!(!success);
    assert!(message.contains("заблокированы"));
}

#[tokio::test]
async fn balance_can_never_go_negative() {
    let db = database().await;
    db.register_user(1, None).await.unwrap();
    db.give_balance(100, 1).await.unwrap();

    assert!(!db.take_balance(101, 1).await.unwrap());
    assert_eq!(db.get_user_stats(1).await.unwrap().balance, 100);

    assert!(db.take_balance(100, 1).await.unwrap());
    assert_eq!(db.get_user_stats(1).await.unwrap().balance, 0);
}

#[tokio::test]
async fn priority_messages_are_consumed_at_most_once() {
    let db = database().await;
    db.register_user(1, None).await.unwrap();

    assert!(!db.waste_priority_message(1).await.unwrap());

    db.increment_priority_messages(1).await.unwrap();
    assert_eq!(db.get_user_stats(1).await.unwrap().priority_messages, 1);

    assert!(db.waste_priority_message(1).await.unwrap());
    assert!(!db.waste_priority_message(1).await.unwrap());
}

#[tokio::test]
async fn only_known_settings_can_be_updated() {
    let db = database().await;
    db.register_user(1, None).await.unwrap();

    db.update_user_setting(1, "show_air", "0").await.unwrap();
    db.update_user_setting(1, "code_auto_refresh", "daily")
        .await
        .unwrap();
    let stats = db.get_user_stats(1).await.unwrap();

    assert!(!stats.show_air);
    assert_eq!(stats.code_auto_refresh, "daily");

    assert!(db.update_user_setting(1, "balance", "1000").await.is_err());
}

#[tokio::test]
async fn message_mappings_survive_code_changes() {
    let db = database().await;
    let stats = db.register_user(1, None).await.unwrap();
    db.add_message(100, 1, &stats.anon_code, true, 7)
        .await
        .unwrap();

    assert_eq!(
        db.get_admin_msg_id_by_user_msg_id(1, 7).await.unwrap(),
        Some(100)
    );
    let sender = db
        .get_sender_with_message_by_admin_msg(100)
        .await
        .unwrap()
        .expect("stored message");
    assert_eq!(sender.sender_id, 1);
    assert_eq!(sender.user_msg_id, 7);

    let with_code = db
        .get_sender_with_code_by_admin_msg(100)
        .await
        .unwrap()
        .expect("stored code");
    assert_eq!(with_code.sender_id, 1);
    assert_eq!(with_code.anon_code, stats.anon_code);
}

#[tokio::test]
async fn payments_are_created_once_and_transitions_are_conditional() {
    let db = database().await;
    db.register_user(1, None).await.unwrap();

    assert!(
        db.create_payment("charge-1", 1, "deposit_100")
            .await
            .unwrap()
    );
    assert!(
        !db.create_payment("charge-1", 1, "deposit_100")
            .await
            .unwrap()
    );

    let payment = db
        .get_payment_by_charge_id("charge-1")
        .await
        .unwrap()
        .expect("stored payment");
    assert_eq!(payment.user_id, 1);
    assert_eq!(payment.payload.as_deref(), Some("deposit_100"));
    assert_eq!(payment.status, "success");
    assert_eq!(
        db.get_payment_user_id_by_charge_id("charge-1")
            .await
            .unwrap(),
        Some(1)
    );
    assert_eq!(
        db.get_success_charge_ids_by_user_id(1).await.unwrap(),
        vec!["charge-1"]
    );

    assert!(
        !db.set_payment_status_if_current("charge-1", "refunded", "success")
            .await
            .unwrap()
    );
    assert!(
        db.set_payment_status_if_current("charge-1", "success", "refunded")
            .await
            .unwrap()
    );
    assert!(
        db.get_success_charge_ids_by_user_id(1)
            .await
            .unwrap()
            .is_empty()
    );

    db.set_payment_status_by_charge_id("charge-1", "success")
        .await
        .unwrap();
    assert_eq!(
        db.get_success_charge_ids_by_user_id(1).await.unwrap(),
        vec!["charge-1"]
    );

    db.batch_set_payment_status_by_charge_ids(&["charge-1".to_string()], "refunded")
        .await
        .unwrap();
    assert!(
        db.get_success_charge_ids_by_user_id(1)
            .await
            .unwrap()
            .is_empty()
    );
    assert!(
        db.batch_set_payment_status_by_charge_ids(&[], "refunded")
            .await
            .is_ok()
    );
}

#[tokio::test]
async fn achievements_are_granted_once_in_order() {
    let db = database().await;
    db.register_user(1, None).await.unwrap();

    db.increment_sent_count(1).await.unwrap();
    db.increment_sent_count(1).await.unwrap();

    let granted = db.check_and_grant_achievements(1).await.unwrap();
    assert_eq!(granted, vec!["anon_first"]);
    assert!(db.check_and_grant_achievements(1).await.unwrap().is_empty());

    assert!(db.grant_achievement(1, "vip_access").await.unwrap());
    assert!(!db.grant_achievement(1, "vip_access").await.unwrap());
    assert_eq!(db.get_user_achievements_count(1).await.unwrap(), 2);

    let mut ids = db.get_user_achievements(1).await.unwrap();
    ids.sort();
    assert_eq!(ids, vec!["anon_first", "vip_access"]);

    assert!(
        db.check_and_grant_achievements(999)
            .await
            .unwrap()
            .is_empty()
    );
}

#[tokio::test]
async fn ids_and_codes_resolve_to_the_same_user() {
    let db = database().await;
    let stats = db.register_user(1, None).await.unwrap();

    assert_eq!(db.get_user_id_by_id_or_code("1").await.unwrap(), Some(1));
    assert_eq!(
        db.get_user_id_by_id_or_code(&stats.anon_code.to_lowercase())
            .await
            .unwrap(),
        Some(1)
    );
    assert_eq!(db.get_user_id_by_id_or_code(" 1 ").await.unwrap(), Some(1));
    assert_eq!(db.get_user_id_by_id_or_code("404").await.unwrap(), None);

    db.ban_user(1, "BANNED01").await.unwrap();
    assert_eq!(
        db.get_user_id_by_id_or_code("BANNED01").await.unwrap(),
        Some(1)
    );
}
