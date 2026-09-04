from nicegui import ui


@ui.page('/', favicon='/static/favicon.ico')
def home_page() -> None:
    ui.add_head_html(
        '<link rel="stylesheet" href="/static/retro.css">'
    )

    with ui.element('div').classes('wb-root'):
        # App header bar
        with ui.element('div').classes('wb-app-header'):
            ui.label('HITBASIC').classes('app-title')
            ui.label('EDITOR v1.0').classes('app-version')

        # Main content area
        with ui.element('div').style('flex:1;display:flex;align-items:center;justify-content:center;'):
            with ui.element('div').classes('wb-window').style('width:480px;'):
                with ui.element('div').classes('wb-title-bar'):
                    ui.label('Welcome').classes('title-text')
                with ui.element('div').style('padding:24px;text-align:center;'):
                    ui.label('HITBASIC EDITOR').style(
                        'font-family:var(--wb-font);font-size:14px;color:var(--wb-blue);'
                        'margin-bottom:16px;display:block;'
                    )
                    ui.label('A retro-styled code editor').style(
                        'font-family:var(--wb-font);font-size:8px;color:#555;'
                        'display:block;margin-bottom:20px;'
                    )
                    ui.label(
                        'Multiple files in memory with browser persistence.\n'
                        'Syntax highlighting and autocomplete hints.\n'
                        'Contextual tips panel for coding help.'
                    ).style(
                        'font-family:var(--wb-font);font-size:8px;color:#333;'
                        'line-height:2;display:block;margin-bottom:24px;white-space:pre-line;'
                    )

                    with ui.element('div').style('display:flex;gap:8px;justify-content:center;'):
                        ui.button(
                            'OPEN EDITOR',
                            on_click=lambda: ui.navigate.to('/editor'),
                        ).classes('wb-button')

                    ui.element('br')
                    ui.label(
                        'Your files are saved in the browser.\nNothing is sent to any server.'
                    ).style(
                        'font-family:var(--wb-font);font-size:7px;color:#888;'
                        'display:block;margin-top:16px;white-space:pre-line;'
                    )
