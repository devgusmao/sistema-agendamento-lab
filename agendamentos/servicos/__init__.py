"""Regras de negócio do sistema, fora das views.

As views só tratam de requisição/resposta (permissão, formulário, mensagem,
redirecionamento); as regras de reserva, cobrança, multa, pagamento e
solicitações ficam aqui, onde podem ser testadas sem passar pelo HTTP.
"""
