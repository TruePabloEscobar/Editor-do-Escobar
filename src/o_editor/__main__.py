"""CLI entry point."""

from __future__ import annotations

import argparse
from collections.abc import Sequence


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Editor Do Escobar — EDE, edição local")
    parser.add_argument("--mock", action="store_true", help="usar a integração simulada")
    parser.add_argument(
        "--headless",
        action="store_true",
        help="executar demonstração sem interface",
    )
    parser.add_argument(
        "--launch-context",
        "--context",
        dest="launch_context",
        help="arquivo de contexto criado pelo launcher",
    )
    parser.add_argument(
        "--internal-host",
        action="store_true",
        help="usar exclusivamente o contexto capturado dentro do DaVinci Resolve",
    )
    action_group = parser.add_mutually_exclusive_group()
    action_group.add_argument(
        "--internal-action-request",
        help="request JSON criada por um comando interno do Resolve",
    )
    action_group.add_argument("--show-report", help="abrir e exibir um relatório na interface")
    action_group.add_argument("--show-message", help="mostrar uma mensagem na interface")
    action_group.add_argument("--diagnostic-result", help="exibir um diagnóstico interno")
    action_group.add_argument("--capability-result", help="exibir um capability probe interno")
    action_group.add_argument("--apply-result", help="exibir um preflight de aplicação")
    parser.add_argument("--self-test", action="store_true", help="executar autodiagnóstico seguro")
    parser.add_argument(
        "--resolve",
        action="store_true",
        help="incluir conexão somente leitura com o Resolve no self-test",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.internal_host and not args.launch_context:
        print("--internal-host exige --launch-context PATH.")
        return 1
    if args.internal_host and args.mock:
        print("--internal-host não pode ser combinado com --mock.")
        return 1
    if args.headless and (
        args.internal_action_request
        or args.show_report
        or args.show_message
        or args.diagnostic_result
        or args.capability_result
        or args.apply_result
    ):
        print("Ações internas visíveis não podem ser combinadas com --headless.")
        return 1
    if args.resolve and not args.self_test:
        print("--resolve só pode ser usado com --self-test.")
        return 1
    if args.self_test:
        from o_editor.bootstrap import project_root
        from o_editor.self_test import run_self_test

        try:
            checks = run_self_test(project_root(), include_resolve=args.resolve)
        except (OSError, RuntimeError, ValueError) as exc:
            print(f"Self-test falhou: {exc}")
            return 1
        for check in checks:
            print(f"[{check.status}] {check.name}: {check.detail}")
        failed = any(check.status == "FAILED" for check in checks)
        print(f"Self-test: {'FAILED' if failed else 'PASSED'}")
        return 1 if failed else 0
    if args.headless:
        from o_editor.bootstrap import run_headless

        return run_headless(use_mock=args.mock, context_path=args.launch_context)

    from o_editor.ui.internal_action_runtime import run_ui

    return run_ui(
        use_mock=args.mock,
        context_path=args.launch_context,
        internal_host=args.internal_host,
        internal_action_request=args.internal_action_request,
        show_report=args.show_report,
        show_message=args.show_message,
        diagnostic_result=args.diagnostic_result,
        capability_result=args.capability_result,
        apply_result=args.apply_result,
    )


if __name__ == "__main__":
    raise SystemExit(main())
