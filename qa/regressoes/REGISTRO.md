# Registro

| ID | Defeito confirmado | Severidade | Status | Proteção |
|---|---|---|---|---|
| [BUG-0001](casos/BUG-0001.md) | Transcrição bloqueada pela duração da primeira pista de áudio | alta | VALIDADO_AUTOMATICAMENTE | tests/integration/test_obs_audio.py::test_short_audio_tail_keeps_timeline_alignment |
| [BUG-0002](casos/BUG-0002.md) | Mapeamento de múltiplas pistas escolhe a primeira pista | alta | VALIDADO_AUTOMATICAMENTE | tests/integration/test_obs_audio.py::test_mapping_uses_actual_embedded_stream |

| [BUG-0003](casos/BUG-0003.md) | Retorno do Rough Cut bloqueado no IPC e fora da prévia | alta | VALIDADO | tests/integration/test_local_ipc.py; tests/ui/test_rough_cut_feedback.py |
| [BUG-0004](casos/BUG-0004.md) | Itens de áudio criados sem retorno bloqueiam a reconstrução | alta | VALIDADO | tests/integration/test_lua_rough_cut.py::test_unreported_audio_items_do_not_block_following_operations |
| [BUG-0005](casos/BUG-0005.md) | Leitura truncada de frame de origem em 23.976 | alta | VALIDADO | tests/integration/test_lua_rough_cut.py::test_source_frame_rounding_requires_independent_agreement |
| [BUG-0006](casos/BUG-0006.md) | Prévia substituída e espera invisível durante pedido pendente | alta | VALIDADO | tests/ui/test_rough_cut_lifecycle.py |

| [BUG-0007](casos/BUG-0007.md) | Faixa 1 reinserida em A1–A4 apesar de JSON distinto | alta | VALIDADO_AUTOMATICAMENTE; ESCUTA PENDENTE | tests/integration/test_lua_rough_cut.py::test_poly_audio_preserves_native_stream_provenance |

| [BUG-0008](casos/BUG-0008.md) | Contexto antigo e prévia conservada após trocar clipes | média | VALIDADO | tests/ui/test_timeline_refresh.py; tests/unit/test_native_bridge.py |

| [BUG-0009](casos/BUG-0009.md) | Plano parte de getter truncado | alta | VALIDADO_AUTOMATICAMENTE | test_source_inpoint_prefers_agreeing_offset_and_rational_time |
| [BUG-0010](casos/BUG-0010.md) | Falha deixa cópia parcial ativa | alta | VALIDADO_AUTOMATICAMENTE | test_failure_returns_to_verified_original_instead_of_incomplete_copy |
| [BUG-0011](casos/BUG-0011.md) | Slip/canais alterados não invalidam plano | alta | VALIDADO_AUTOMATICAMENTE | test_source_slip_or_routing_change_blocks_before_copy |

| [BUG-0012](casos/BUG-0012.md) | Recibo ausente perde resposta após aplicar | alta | VALIDADO_AUTOMATICAMENTE | test_confirmed_button_dispatches_script_and_receives_result_without_menu |

| [BUG-0013](casos/BUG-0013.md) | Janela fechada consome replies de outra | média | VALIDADO_AUTOMATICAMENTE | test_closed_window_stops_polling_and_does_not_steal_another_reply |

| [BUG-0014](casos/BUG-0014.md) | Estado ativo/desativado não conferido | alta | VALIDADO_AUTOMATICAMENTE | tests/integration/test_lua_rough_cut.py::test_microphone_clip_states_are_verified_and_original_is_intact |

| [BUG-0015](casos/BUG-0015.md) | Manifesto do instalador conserva release antiga | média | VALIDADO_AUTOMATICAMENTE | tests/integration/test_launcher_installation.py::test_installer_manifest_tracks_source_release_instead_of_stale_constant |

| [BUG-0016](casos/BUG-0016.md) | Getter final truncado rejeita clipe curto normal | alta | VALIDADO_AUTOMATICAMENTE | tests/unit/test_timeline_layout.py::test_short_native_clip_with_truncated_end_requires_independent_time |

| [BUG-0017](casos/BUG-0017.md) | Executor técnico real trava ao alternar timelines | alta | PENDENTE_DE_AUTOMACAO | Probe manual em projeto descartável; causa do host não resolvida |

| [BUG-0018](casos/BUG-0018.md) | Cache conserva texto ao trocar modelo local | média | VALIDADO | tests/integration/test_transcription_model_cache.py; tests/unit/test_transcription_settings.py |

| [BUG-0019](casos/BUG-0019.md) | Ações cobrem a tabela de faixas em janela pequena | média | VALIDADO | tests/ui/test_ede_settings.py::test_track_selection_actions_do_not_cover_the_table |

| [BUG-0020](casos/BUG-0020.md) | Retorno digital em volume igual permanece ativo | média | VALIDADO_AUTOMATICAMENTE | tests/integration/test_identical_microphones.py |

| [BUG-0021](casos/BUG-0021.md) | Planejamento reexamina todos os mutes por clipe | média | VALIDADO_AUTOMATICAMENTE | tests/unit/test_planner_scaling.py |

| [BUG-0022](casos/BUG-0022.md) | Instalador legado aponta para Python fora do destino | alta | VALIDADO_AUTOMATICAMENTE | tests/integration/test_legacy_installer.py |

| [BUG-0023](casos/BUG-0023.md) | Ferramentas com avisos conhecidos de segurança | média | VALIDADO_AUTOMATICAMENTE | tests/unit/test_packaging_security.py |

| [BUG-0024](casos/BUG-0024.md) | Resposta malformada de download gera exceção na GUI | baixa | VALIDADO_AUTOMATICAMENTE | tests/ui/test_download_and_about.py |

| [BUG-0025](casos/BUG-0025.md) | Cópia extraída duplica fontes na cobertura | baixa | VALIDADO_AUTOMATICAMENTE | tests/integration/test_distribution.py; scripts/run_regression.py |

| [BUG-0026](casos/BUG-0026.md) | Referência omitida/muda silencia a cópia audível | alta | VALIDADO_AUTOMATICAMENTE | tests/integration/test_identical_microphones.py |

| [BUG-0027](casos/BUG-0027.md) | Metadados Python gerados entram no ZIP | baixa | VALIDADO_AUTOMATICAMENTE | tests/integration/test_distribution.py |
