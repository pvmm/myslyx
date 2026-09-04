// HITBASIC Editor - localStorage persistence & editor helpers
(function() {
    'use strict';

    const STORAGE_KEY = 'wb_editor_files';
    const ACTIVE_KEY = 'wb_editor_active';

    // ===== File Pool Management via localStorage =====

    window.WBStorage = {
        loadFiles: function() {
            try {
                const raw = localStorage.getItem(STORAGE_KEY);
                if (raw) return JSON.parse(raw);
            } catch(e) {
                console.warn('WBStorage: failed to load files', e);
            }
            return null;
        },

        saveFiles: function(files) {
            try {
                localStorage.setItem(STORAGE_KEY, JSON.stringify(files));
            } catch(e) {
                console.warn('WBStorage: failed to save files', e);
            }
        },

        loadActive: function() {
            return localStorage.getItem(ACTIVE_KEY) || null;
        },

        saveActive: function(id) {
            localStorage.setItem(ACTIVE_KEY, id);
        },

        clear: function() {
            localStorage.removeItem(STORAGE_KEY);
            localStorage.removeItem(ACTIVE_KEY);
        },

        generateId: function() {
            return 'file_' + Date.now() + '_' + Math.random().toString(36).substr(2, 6);
        }
    };

    // ===== Default starter files =====

    window.WBDefaults = {
        createStarterFiles: function() {
            return [
                {
                    id: WBStorage.generateId(),
                    name: 'hello.py',
                    language: 'Python',
                    content: [
                        '#!/usr/bin/env python3',
                        '"""Welcome to HITBASIC Editor"""',
                        '',
                        'def greet(name):',
                        '    """Print a friendly greeting."""',
                        '    print(f"Hello, {name}!")',
                        '    print("Welcome to HITBASIC.")',
                        '',
                        '',
                        'if __name__ == "__main__":',
                        '    greet("User")',
                    ].join('\n')
                },
                {
                    id: WBStorage.generateId(),
                    name: 'notes.txt',
                    language: 'Text',
                    content: [
                        '=== HITBASIC EDITOR ===',
                        '',
                        'Features:',
                        '  - Multiple files in memory',
                        '  - Syntax highlighting',
                        '  - Autocomplete hints',
                        '  - Context tips panel',
                        '',
                        'Files persist in browser localStorage.',
                        'Switch files using the dock at the bottom.',
                    ].join('\n')
                },
                {
                    id: WBStorage.generateId(),
                    name: 'script.js',
                    language: 'JavaScript',
                    content: [
                        '// Sample JavaScript file',
                        '',
                        'function fibonacci(n) {',
                        '    if (n <= 1) return n;',
                        '    return fibonacci(n - 1) + fibonacci(n - 2);',
                        '}',
                        '',
                        'const result = fibonacci(10);',
                        'console.log(`Fibonacci(10) = ${result}`);',
                    ].join('\n')
                }
            ];
        }
    };

    // ===== Language-specific hint data =====

    window.WBHints = {
        python: {
            keywords: ['def', 'class', 'if', 'elif', 'else', 'for', 'while', 'return',
                       'import', 'from', 'as', 'try', 'except', 'finally', 'with',
                       'yield', 'lambda', 'pass', 'break', 'continue', 'raise',
                       'True', 'False', 'None', 'and', 'or', 'not', 'in', 'is'],
            builtins: ['print', 'len', 'range', 'str', 'int', 'float', 'list', 'dict',
                      'set', 'tuple', 'type', 'isinstance', 'input', 'open', 'enumerate',
                      'zip', 'map', 'filter', 'sorted', 'reversed', 'super', 'property'],
            tips: {
                'def': 'Define a function: def name(args):\nIndent the body with 4 spaces.',
                'class': 'Define a class: class Name:\nUse __init__ for constructor.',
                'if': 'Conditional: if condition:\nUse elif/else for branches.',
                'for': 'Loop: for item in iterable:\nUse range() for numeric loops.',
                'while': 'Loop: while condition:\nBe careful of infinite loops.',
                'return': 'Return a value from a function.\nBare return returns None.',
                'import': 'Import a module: import module\nOr: from module import name',
                'try': 'Exception handling:\ntry:\n    ...\nexcept Error:\n    ...',
                'with': 'Context manager: with open(f) as fh:\nAuto-closes resource.',
                'lambda': 'Anonymous function: lambda x: x + 1\nUse for small callbacks.',
                'print': 'Output to stdout: print("hello")\nUse sep and end kwargs.',
                'len': 'Get length: len(collection)\nWorks on strings, lists, dicts.',
                'range': 'Numeric sequence: range(start, stop, step)\nExclusive of stop.',
                'list': 'List constructor: list() or [1, 2, 3]\nMutable sequence type.',
                'dict': 'Dictionary: dict() or {"key": val}\nKey-value pairs.',
                'None': 'Python\'s null value. Represents absence of a value.',
                'True': 'Boolean true. Also used as 1 in arithmetic.',
                'False': 'Boolean false. Also used as 0 in arithmetic.',
                'class': 'Define a class. Use PascalCase naming.',
                'self': 'First param of methods. Refers to the instance.',
                'is': 'Identity comparison: a is b\nChecks if same object, not equal value.',
                '__init__': 'Constructor method. Called when creating an instance.',
            },
            patterns: [
                { re: 'def\\s+(\\w+)', tip: 'Defining function. Add a docstring!' },
                { re: 'class\\s+(\\w+)', tip: 'Defining a class. Use PascalCase.' },
                { re: 'print\\s*\\(', tip: 'print() outputs to stdout. Use f-strings for formatting.' },
                { re: 'for\\s+\\w+\\s+in\\s+range', tip: 'range() is exclusive of the stop value.' },
                { re: 'except\\s*:', tip: 'Bare except catches all. Consider except Exception:' },
                { re: '=\\s*\\[', tip: 'List comprehension: [expr for x in iter if cond]' },
                { re: 'import\\s+\\w+', tip: 'Tip: use "from x import y" for specific imports.' },
            ]
        },
        javascript: {
            keywords: ['function', 'const', 'let', 'var', 'if', 'else', 'for', 'while',
                       'return', 'class', 'extends', 'new', 'this', 'import', 'export',
                       'default', 'from', 'async', 'await', 'try', 'catch', 'throw',
                       'typeof', 'instanceof', 'switch', 'case', 'break', 'continue',
                       'true', 'false', 'null', 'undefined', 'of', 'in'],
            builtins: ['console', 'Math', 'JSON', 'Array', 'Object', 'String', 'Number',
                      'Promise', 'Date', 'Map', 'Set', 'RegExp', 'Error', 'parseInt',
                      'parseFloat', 'setTimeout', 'setInterval', 'fetch', 'document',
                      'window', 'alert', 'confirm', 'prompt', 'require', 'module'],
            tips: {
                'const': 'Constant binding. Cannot be reassigned.\nUse for values that don\'t change.',
                'let': 'Block-scoped variable.\nUse instead of var for modern code.',
                'var': 'Function-scoped variable. Avoid using.\nUse const/let instead.',
                'function': 'Function declaration. Also try arrow functions: () => {}',
                'class': 'Class declaration. Use PascalCase.\nAdd constructor() method.',
                'async': 'Makes function return a Promise.\nUse with await for async operations.',
                'await': 'Waits for a Promise to resolve.\nOnly usable inside async functions.',
                'import': 'ES6 module import.\nimport name from "module"',
                'export': 'Export from module.\nexport default name / export { name }',
                'this': 'Refers to calling context.\nIn classes: the instance.\nIn functions: depends on call.',
                'console': 'Debugging: console.log(), .warn(), .error()\nAvailable in browser & Node.',
                'fetch': 'HTTP requests: fetch(url).then(r => r.json())\nReturns a Promise.',
                'Promise': 'Async computation: new Promise((res, rej) => {})\nAlso: .then()/.catch().',
                'typeof': 'Returns type as string: typeof x === "string"\nUse for type checking.',
                'null': 'Intentional absence of value.\nDistinct from undefined.',
                'undefined': 'Variable declared but not assigned.\nAlso: missing function return.',
                'true': 'Boolean true literal. Cannot be reassigned.',
                'false': 'Boolean false literal. Cannot be reassigned.',
                'return': 'Returns value from function.\nBare return returns undefined.',
                '=>': 'Arrow function: (x) => x * 2\nConcise syntax, lexical this.',
                '===': 'Strict equality. No type coercion.\nAlways prefer over ==.',
            },
            patterns: [
                { re: 'function\\s+(\\w+)', tip: 'Defining a function. Consider if arrow function fits.' },
                { re: 'class\\s+(\\w+)', tip: 'Defining a class. Add constructor and methods.' },
                { re: 'console\\.(log|warn|error)', tip: 'Remember to remove console statements before shipping!' },
                { re: '==(?!=)', tip: 'Use === (strict equality) instead of == for safety.' },
                { re: 'var\\s+', tip: 'Prefer const or let over var for block scoping.' },
                { re: 'async', tip: 'async functions return a Promise. Use await inside.' },
                { re: 'new\\s+Promise', tip: 'Promises: prefer async/await over .then() chains.' },
                { re: 'document\\.', tip: 'DOM manipulation. Consider using querySelector().' },
            ]
        },
        plaintext: {
            keywords: [],
            builtins: [],
            tips: {},
            patterns: []
        },
        typescript: {
            keywords: ['function', 'const', 'let', 'var', 'if', 'else', 'for', 'while',
                       'return', 'class', 'extends', 'new', 'this', 'import', 'export',
                       'default', 'from', 'async', 'await', 'try', 'catch', 'throw',
                       'typeof', 'instanceof', 'switch', 'case', 'break', 'continue',
                       'true', 'false', 'null', 'undefined', 'interface', 'type',
                       'enum', 'namespace', 'declare', 'abstract', 'implements',
                       'readonly', 'private', 'protected', 'public', 'static', 'as',
                       'keyof', 'never', 'any', 'unknown', 'void'],
            builtins: ['Array', 'Object', 'String', 'Number', 'Boolean', 'Map', 'Set',
                      'Promise', 'Record', 'Partial', 'Required', 'Pick', 'Omit',
                      'Exclude', 'Extract', 'ReturnType', 'Parameters', 'Partial',
                      'Readonly', 'Pick', 'Omit', 'Re',
                      'console', 'JSON', 'Math', 'Date', 'Error', 'RegExp'],
            tips: {
                'interface': 'Define an interface: interface Name { prop: type }\nUse for object shapes.',
                'type': 'Type alias: type Name = ...\nUse for unions, intersections, primitives.',
                'enum': 'Enumeration: enum Color { Red, Green, Blue }\nNumeric or string values.',
                'readonly': 'Readonly modifier. Property cannot be reassigned.',
                'private': 'Private modifier. Only accessible within the class.',
                'protected': 'Protected modifier. Accessible in class and subclasses.',
                'public': 'Public modifier. Accessible anywhere (default).',
                'abstract': 'Abstract class/method. Must be implemented by subclasses.',
                'implements': 'Class implements interface: class C implements I {}',
                'any': 'Any type. Avoid using - defeats type checking.',
                'unknown': 'Type-safe any. Must narrow before using.',
                'void': 'No return value. Use for functions that return nothing.',
                'never': 'Never returns. Used for functions that throw or infinite loops.',
                'keyof': 'Keyof operator: keyof T = union of keys of T',
                'as': 'Type assertion: value as Type\nOr import renaming: import { X as Y }',
                'const': 'Cannot be reassigned. Use for values that don\'t change.',
                'let': 'Block-scoped variable. Reassignable.',
                'function': 'Function declaration. Also try arrow functions: () => {}',
                'class': 'Class declaration. Use PascalCase.',
                'async': 'Makes function return a Promise.',
                'await': 'Waits for a Promise. Only inside async functions.',
                'import': 'ES6 import: import { name } from "module"',
                'export': 'Export: export default name / export { name }',
                'Promise': 'Async: new Promise<T>((res, rej) => {})',
                'Record': 'Utility: Record<K, V> = object with keys K, values V',
                'Partial': 'All properties optional: Partial<T>',
                'Required': 'All properties required: Required<T>',
                'Pick': 'Select properties: Pick<T, "a" | "b">',
                'Omit': 'Remove properties: Omit<T, "a">',
            },
            patterns: [
                { re: 'interface\\s+(\\w+)', tip: 'Defining an interface. Define object shape.' },
                { re: 'type\\s+(\\w+)', tip: 'Defining a type alias.' },
                { re: 'enum\\s+(\\w+)', tip: 'Defining an enum. Consider const enum for tree-shaking.' },
                { re: ':\\s*any\\b', tip: 'Avoid "any" - use "unknown" and narrow the type.' },
                { re: 'as\\s+\\w+', tip: 'Type assertion. Prefer type guards when possible.' },
                { re: 'async', tip: 'async functions return Promise. Use await inside.' },
                { re: '==(?!=)', tip: 'Use === (strict equality) in TypeScript.' },
            ]
        }
    };

})();
